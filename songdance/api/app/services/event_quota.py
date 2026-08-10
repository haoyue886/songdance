import threading
import time
from dataclasses import dataclass

from redis import Redis

from app.settings import Settings


@dataclass(frozen=True)
class EventQuotaExceeded(Exception):
    code: str
    message: str
    retry_after: int


class MemoryEventQuota:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._event_lock = threading.Lock()
        self._event_minute = ""
        self._event_counts: dict[str, int] = {}
        self._event_day = ""
        self._event_daily = 0

    def reserve_event(self, job_key: str, client_key: str) -> None:
        now = time.time()
        minute = time.strftime("%Y%m%d%H%M", time.gmtime(now))
        day = time.strftime("%Y%m%d", time.gmtime(now))
        with self._event_lock:
            if minute != self._event_minute:
                self._event_minute = minute
                self._event_counts.clear()
            if day != self._event_day:
                self._event_day = day
                self._event_daily = 0
            checks = (
                (f"job:{job_key}", self.settings.analytics_job_event_limit_per_minute, 1),
                (f"client:{client_key}", self.settings.analytics_client_event_limit_per_minute, 2),
                ("global", self.settings.analytics_global_event_limit_per_minute, 3),
            )
            for key, limit, code in checks:
                if self._event_counts.get(key, 0) >= limit:
                    raise event_quota_error(code, now)
            if self._event_daily >= self.settings.analytics_daily_event_limit:
                raise event_quota_error(4, now)
            for key, _limit, _code in checks:
                self._event_counts[key] = self._event_counts.get(key, 0) + 1
            self._event_daily += 1


EVENT_RESERVE_SCRIPT = """
for index = 1, 3 do
  if tonumber(redis.call('GET', KEYS[index]) or '0') >= tonumber(ARGV[index]) then
    return index
  end
end
if tonumber(redis.call('GET', KEYS[4]) or '0') >= tonumber(ARGV[4]) then return 4 end
for index = 1, 3 do
  redis.call('INCR', KEYS[index]); redis.call('EXPIRE', KEYS[index], tonumber(ARGV[5]))
end
redis.call('INCR', KEYS[4]); redis.call('EXPIRE', KEYS[4], tonumber(ARGV[6]))
return 0
"""


class RedisEventQuota:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis = Redis.from_url(str(settings.redis_url), decode_responses=True)

    def reserve_event(self, job_key: str, client_key: str) -> None:
        now = time.time()
        minute = time.strftime("%Y%m%d%H%M", time.gmtime(now))
        day = time.strftime("%Y%m%d", time.gmtime(now))
        prefix = f"songdance:{self.settings.quota_namespace}:events"
        code = int(
            self.redis.eval(
                EVENT_RESERVE_SCRIPT,
                4,
                f"{prefix}:minute:{minute}:job:{job_key}",
                f"{prefix}:minute:{minute}:client:{client_key}",
                f"{prefix}:minute:{minute}:global",
                f"{prefix}:day:{day}",
                self.settings.analytics_job_event_limit_per_minute,
                self.settings.analytics_client_event_limit_per_minute,
                self.settings.analytics_global_event_limit_per_minute,
                self.settings.analytics_daily_event_limit,
                120,
                90000,
            )
        )
        if code:
            raise event_quota_error(code, now)


def event_quota_error(code: int, now: float) -> EventQuotaExceeded:
    errors = {
        1: ("EVENT_JOB_LIMIT", "这个任务的事件记录已达到上限", 60 - int(now) % 60),
        2: ("EVENT_CLIENT_LIMIT", "事件记录过于频繁", 60 - int(now) % 60),
        3: ("EVENT_GLOBAL_LIMIT", "事件服务当前已满", 60 - int(now) % 60),
        4: ("EVENT_DAILY_LIMIT", "今日事件记录额度已用完", _day_retry(now)),
    }
    error_code, message, retry_after = errors[code]
    return EventQuotaExceeded(error_code, message, max(1, retry_after))


def _day_retry(now: float) -> int:
    return max(1, 86400 - int(now) % 86400)

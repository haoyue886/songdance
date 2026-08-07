import hashlib
import hmac
import ipaddress
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

from app.services.event_quota import MemoryEventQuota, RedisEventQuota
from app.settings import Settings


@dataclass(frozen=True)
class QuotaExceeded(Exception):
    code: str
    message: str
    retry_after: int


class JobQuota(Protocol):
    def reserve(self, job_id: str, client_key: str) -> None: ...

    def cancel(self, job_id: str) -> None: ...

    def complete(self, job_id: str) -> None: ...

    def reserve_event(self, job_key: str, client_key: str) -> None: ...


def client_quota_key(request: Request, settings: Settings) -> str:
    host = request.client.host if request.client else "unknown"
    try:
        peer_address = ipaddress.ip_address(host)
    except ValueError:
        peer_address = None
    trusted_peer = peer_address is not None and any(
        peer_address in network for network in settings.trusted_proxy_networks
    )
    if settings.trusted_proxy_hops and trusted_peer:
        forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",")]
        forwarded = [part for part in forwarded if part]
        if len(forwarded) >= settings.trusted_proxy_hops:
            candidate = forwarded[-settings.trusted_proxy_hops]
            try:
                host = ipaddress.ip_address(candidate).compressed
            except ValueError:
                pass
    secret = settings.download_signing_secret.get_secret_value().encode()
    return hmac.new(secret, host.encode(), hashlib.sha256).hexdigest()


class MemoryJobQuota(MemoryEventQuota):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._lock = threading.Lock()
        self._jobs: dict[str, tuple[str, str, str, float]] = {}
        self._hourly: dict[str, int] = {}
        self._daily: dict[str, int] = {}

    def reserve(self, job_id: str, client_key: str) -> None:
        now = time.time()
        hour = time.strftime("%Y%m%d%H", time.gmtime(now))
        day = time.strftime("%Y%m%d", time.gmtime(now))
        hour_key = f"{client_key}:{hour}"
        with self._lock:
            self._prune(now)
            client_active = sum(item[0] == client_key for item in self._jobs.values())
            self._check(
                client_active,
                len(self._jobs),
                self._hourly.get(hour_key, 0),
                self._daily.get(day, 0),
                now,
            )
            self._hourly[hour_key] = self._hourly.get(hour_key, 0) + 1
            self._daily[day] = self._daily.get(day, 0) + 1
            self._jobs[job_id] = (
                client_key,
                hour_key,
                day,
                now + self.settings.quota_active_ttl_seconds,
            )

    def cancel(self, job_id: str) -> None:
        with self._lock:
            item = self._jobs.pop(job_id, None)
            if item is None:
                return
            _, hour_key, day, _ = item
            self._hourly[hour_key] = max(0, self._hourly.get(hour_key, 0) - 1)
            self._daily[day] = max(0, self._daily.get(day, 0) - 1)

    def complete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def _prune(self, now: float) -> None:
        self._jobs = {key: value for key, value in self._jobs.items() if value[3] > now}

    def _check(
        self, client_active: int, global_active: int, hourly: int, daily: int, now: float
    ) -> None:
        if hourly >= self.settings.hourly_job_limit:
            raise QuotaExceeded(
                "HOURLY_LIMIT",
                f"每小时最多创建 {self.settings.hourly_job_limit} 个任务",
                _hour_retry(now),
            )
        if client_active >= self.settings.client_active_job_limit:
            raise QuotaExceeded("ACTIVE_JOB_LIMIT", "请等待当前任务结束后再提交", 30)
        if global_active >= self.settings.global_active_job_limit:
            raise QuotaExceeded("GLOBAL_CAPACITY", "服务当前已满，请稍后重试", 60)
        if daily >= self.settings.daily_job_limit:
            raise QuotaExceeded("DAILY_CAPACITY", "今日处理额度已用完", _day_retry(now))


RESERVE_SCRIPT = """
local now = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
if tonumber(redis.call('GET', KEYS[3]) or '0') >= tonumber(ARGV[3]) then return 1 end
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[4]) then return 2 end
if redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[5]) then return 3 end
if tonumber(redis.call('GET', KEYS[4]) or '0') >= tonumber(ARGV[6]) then return 4 end
redis.call('INCR', KEYS[3]); redis.call('EXPIRE', KEYS[3], tonumber(ARGV[7]))
redis.call('INCR', KEYS[4]); redis.call('EXPIRE', KEYS[4], tonumber(ARGV[8]))
redis.call('ZADD', KEYS[1], tonumber(ARGV[2]), ARGV[9])
redis.call('ZADD', KEYS[2], tonumber(ARGV[2]), ARGV[9])
redis.call('SET', KEYS[5], cjson.encode({client=KEYS[1],hour=KEYS[3],day=KEYS[4]}),
           'EX', tonumber(ARGV[10]))
return 0
"""

CANCEL_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local value = cjson.decode(raw)
redis.call('ZREM', value.client, ARGV[1]); redis.call('ZREM', KEYS[2], ARGV[1])
if tonumber(redis.call('GET', value.hour) or '0') > 0 then redis.call('DECR', value.hour) end
if tonumber(redis.call('GET', value.day) or '0') > 0 then redis.call('DECR', value.day) end
redis.call('DEL', KEYS[1]); return 1
"""

COMPLETE_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if raw then
  local value = cjson.decode(raw); redis.call('ZREM', value.client, ARGV[1])
end
redis.call('ZREM', KEYS[2], ARGV[1]); redis.call('DEL', KEYS[1]); return 1
"""


class RedisJobQuota(RedisEventQuota):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    def reserve(self, job_id: str, client_key: str) -> None:
        now = time.time()
        expires = now + self.settings.quota_active_ttl_seconds
        hour = time.strftime("%Y%m%d%H", time.gmtime(now))
        day = time.strftime("%Y%m%d", time.gmtime(now))
        prefix = f"songdance:{self.settings.quota_namespace}"
        keys = [
            f"{prefix}:active:client:{client_key}",
            f"{prefix}:active:global",
            f"{prefix}:hour:{client_key}:{hour}",
            f"{prefix}:day:{day}",
            f"{prefix}:quota-job:{job_id}",
        ]
        code = int(
            self.redis.eval(
                RESERVE_SCRIPT,
                len(keys),
                *keys,
                now,
                expires,
                self.settings.hourly_job_limit,
                self.settings.client_active_job_limit,
                self.settings.global_active_job_limit,
                self.settings.daily_job_limit,
                3700,
                90000,
                job_id,
                self.settings.quota_active_ttl_seconds,
            )
        )
        errors = {
            1: QuotaExceeded(
                "HOURLY_LIMIT",
                f"每小时最多创建 {self.settings.hourly_job_limit} 个任务",
                _hour_retry(now),
            ),
            2: QuotaExceeded("ACTIVE_JOB_LIMIT", "请等待当前任务结束后再提交", 30),
            3: QuotaExceeded("GLOBAL_CAPACITY", "服务当前已满，请稍后重试", 60),
            4: QuotaExceeded("DAILY_CAPACITY", "今日处理额度已用完", _day_retry(now)),
        }
        if code in errors:
            raise errors[code]

    def cancel(self, job_id: str) -> None:
        prefix = f"songdance:{self.settings.quota_namespace}"
        self.redis.eval(
            CANCEL_SCRIPT,
            2,
            f"{prefix}:quota-job:{job_id}",
            f"{prefix}:active:global",
            job_id,
        )

    def complete(self, job_id: str) -> None:
        prefix = f"songdance:{self.settings.quota_namespace}"
        self.redis.eval(
            COMPLETE_SCRIPT,
            2,
            f"{prefix}:quota-job:{job_id}",
            f"{prefix}:active:global",
            job_id,
        )


def create_job_quota(settings: Settings) -> JobQuota:
    return (
        MemoryJobQuota(settings) if settings.quota_backend == "memory" else RedisJobQuota(settings)
    )


def _hour_retry(now: float) -> int:
    return max(1, 3600 - int(now) % 3600)


def _day_retry(now: float) -> int:
    return max(1, 86400 - int(now) % 86400)

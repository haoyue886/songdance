import hashlib
import hmac
from typing import Protocol

from redis import Redis
from rq import Queue, Retry
from rq.job import Callback

from app.settings import Settings


class JobQueue(Protocol):
    def enqueue(self, job_id: str, attempt: int) -> str: ...


class RedisJobQueue:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        connection = Redis.from_url(str(settings.redis_url))
        self.queue = Queue(settings.queue_name, connection=connection)

    def enqueue(self, job_id: str, attempt: int) -> str:
        queue_job = self.queue.enqueue_call(
            func="app.jobs.tasks.verify_source_job",
            args=(job_id, attempt),
            job_id=queue_job_id(job_id, attempt, self.settings),
            meta={"transcription_job_id": job_id, "attempt": attempt},
            retry=Retry(max=2),
            on_failure=Callback("app.jobs.tasks.mark_job_failed"),
            timeout=900,
            result_ttl=3_600,
            failure_ttl=86_400,
        )
        return queue_job.id


def create_job_queue(settings: Settings) -> JobQueue:
    return RedisJobQueue(settings)


def queue_job_id(job_id: str, attempt: int, settings: Settings) -> str:
    secret = settings.download_signing_secret.get_secret_value().encode()
    digest = hmac.new(secret, f"rq:{job_id}:{attempt}".encode(), hashlib.sha256).hexdigest()
    return f"transcription-{digest}"

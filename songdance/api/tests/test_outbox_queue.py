"""Opt-in unique dispatch checks on a test-owned temporary Redis."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError
from rq.job import Job

from app.services.queue import RedisJobQueue, queue_job_id
from app.settings import Settings
from tests.test_paid_quota_redis import temporary_redis as temporary_redis

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to temporary Redis; no existing services are used",
)


@pytest.fixture
def queue_factory(temporary_redis):
    queues = []

    def create(queue_name=None):
        settings = Settings(
            _env_file=None,
            redis_url=temporary_redis,
            queue_name=queue_name or f"outbox-test-{uuid4().hex}",
        )
        queue = RedisJobQueue(settings)
        queues.append(queue)
        return queue

    yield create
    for queue in queues:
        queue.queue.connection.close()


def test_concurrent_dispatches_enqueue_one_copy(queue_factory):
    first = queue_factory()
    second = queue_factory(first.settings.queue_name)
    job_id = uuid4().hex
    barrier = Barrier(2)

    def dispatch(queue):
        barrier.wait(timeout=5)
        return queue.enqueue_unique(job_id, 1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(dispatch, [first, second]))

    expected_id = queue_job_id(job_id, 1, first.settings)
    assert results == [expected_id, expected_id]
    assert first.queue.job_ids == [expected_id]
    job = Job.fetch(expected_id, connection=first.queue.connection)
    assert job.func_name == "app.jobs.tasks.verify_source_job"
    assert job.args == (job_id, 1)
    assert job.retries_left == 2
    assert job.timeout == 900
    assert job.to_dict()["failure_callback_name"] == "app.jobs.tasks.mark_job_failed"


def test_separate_attempts_enqueue_independently(queue_factory):
    queue = queue_factory()
    job_id = uuid4().hex
    first_id = queue.enqueue_unique(job_id, 1)
    second_id = queue.enqueue_unique(job_id, 2)
    assert first_id != second_id
    assert queue.queue.job_ids == [first_id, second_id]
    assert Job.fetch(second_id, connection=queue.queue.connection).args == (job_id, 2)


def test_lost_response_replay_preserves_existing_job_metadata(queue_factory, monkeypatch):
    queue = queue_factory()
    job_id = uuid4().hex
    expected_id = queue_job_id(job_id, 1, queue.settings)
    original_enqueue = queue.queue.enqueue_call

    def enqueue_then_lose_response(*args, **kwargs):
        original_enqueue(*args, **kwargs)
        raise RedisTimeoutError("response lost after Redis accepted the job")

    with monkeypatch.context() as patch:
        patch.setattr(queue.queue, "enqueue_call", enqueue_then_lose_response)
        with pytest.raises(RedisTimeoutError):
            queue.enqueue_unique(job_id, 1)

    accepted_job = Job.fetch(expected_id, connection=queue.queue.connection)
    accepted_job.meta["worker_execution_count"] = 1
    accepted_job.save_meta()
    assert queue.enqueue_unique(job_id, 1) == expected_id
    assert queue.queue.job_ids == [expected_id]
    replayed_job = Job.fetch(expected_id, connection=queue.queue.connection)
    assert replayed_job.meta == {
        "transcription_job_id": job_id,
        "attempt": 1,
        "worker_execution_count": 1,
    }

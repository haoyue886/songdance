from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from sqlalchemy import select

from app.jobs.cleanup import cleanup_expired_jobs
from app.models import (
    JobDispatch,
    JobStatus,
    JobSubmission,
    TranscriptionJob,
    UsageLedger,
    UsagePeriod,
)
from app.services.dispatch import begin_dispatch_run, dispatch_pending
from app.services.transcription_persistence import mark_failed, set_stage
from tests.conftest import wav_bytes
from tests.test_usage_ledger import protected_client as protected_client
from tests.transcription_helpers import fake_transcription, run_service

OWNER = {"Authorization": "Bearer alice"}


@pytest.fixture
def durable(protected_client):
    client = protected_client
    client.app.state.settings.reliable_queue_enabled = True
    client.app.state.settings.usage_enabled = True
    return client


def create(client, key="submit-key-123", token="alice", content=None, **values):
    return client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        files={"audio_file": ("audio.wav", content or wav_bytes(), "audio/wav")},
        data={"start_sec": "0", "end_sec": "2", "rights_confirmed": "true", **values},
    )


def dispatch(client, now=None):
    return dispatch_pending(
        client.app.state.session_factory,
        client.app.state.settings,
        client.app.state.job_queue,
        client.app.state.storage,
        client.app.state.job_quota,
        now=now,
    )


def counters(client):
    with client.app.state.session_factory() as session:
        period = session.scalar(select(UsagePeriod))
        return period.reserved_units, period.consumed_units


def test_replayed_upload_returns_one_job_and_one_reservation(durable):
    first, second = create(durable), create(durable)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert counters(durable) == (1, 0)
    with durable.app.state.session_factory() as session:
        assert len(session.scalars(select(JobSubmission)).all()) == 1
        assert len(session.scalars(select(JobDispatch)).all()) == 1
        assert len(session.scalars(select(UsageLedger)).all()) == 1
    assert len(durable.app.state.job_queue.calls) == 1


def test_key_conflict_and_cross_account_isolation(durable):
    first = create(durable)
    assert first.status_code == 201
    assert create(durable, end_sec="1").status_code == 409
    assert create(durable, content=wav_bytes(frequency=440)).status_code == 409
    second = create(durable, token="bob")
    assert second.status_code == 201 and second.json()["id"] != first.json()["id"]


def test_failed_publish_remains_durable_and_recovers_without_recharging(durable):
    queue = durable.app.state.job_queue
    queue.error = ConnectionError("redis unavailable")
    first = create(durable)
    assert first.status_code == 201 and first.json()["status"] == "queued"
    job_id = first.json()["id"]
    assert counters(durable) == (1, 0)
    with durable.app.state.session_factory() as session:
        row = session.scalar(select(JobDispatch))
        assert row.status == "pending" and row.error_code == "QUEUE_UNAVAILABLE"
    queue.error = None
    assert dispatch(durable, datetime.now(UTC) + timedelta(seconds=10)) == 1
    assert queue.calls == [(job_id, 1)]
    assert create(durable).json()["id"] == job_id
    assert counters(durable) == (1, 0)


def test_redis_accepts_then_response_is_lost_replay_is_safe(durable, monkeypatch):
    queue = durable.app.state.job_queue
    enqueue = queue.enqueue_unique

    def lose_ack(job_id, attempt):
        enqueue(job_id, attempt)
        raise ConnectionError("lost ack")

    monkeypatch.setattr(queue, "enqueue_unique", lose_ack)
    job_id = create(durable).json()["id"]
    monkeypatch.setattr(queue, "enqueue_unique", enqueue)
    dispatch(durable, datetime.now(UTC) + timedelta(seconds=10))
    assert queue.calls == [(job_id, 1)] and counters(durable) == (1, 0)


def test_interrupted_after_storage_put_recovers_verified_source(durable, monkeypatch):
    from app.services import durable_jobs

    original = durable_jobs.ready_dispatch
    monkeypatch.setattr(
        durable_jobs,
        "ready_dispatch",
        lambda *_: (_ for _ in ()).throw(RuntimeError("process interruption")),
    )
    assert create(durable).status_code == 503
    monkeypatch.setattr(durable_jobs, "ready_dispatch", original)
    first = create(durable)
    assert first.status_code == 201 and first.json()["stage"] == "upload"
    now = datetime.now(UTC) + timedelta(
        seconds=durable.app.state.settings.upload_intent_timeout_seconds + 1
    )
    dispatch(durable, now)
    assert durable.app.state.job_queue.calls == [(first.json()["id"], 1)]
    assert counters(durable) == (1, 0)


def test_missing_upload_fails_and_releases_once_without_dispatching(durable, monkeypatch):
    monkeypatch.setattr(
        durable.app.state.storage,
        "put_file",
        lambda *_: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    assert create(durable).status_code == 503
    now = datetime.now(UTC) + timedelta(minutes=16)
    dispatch(durable, now)
    dispatch(durable, now)
    assert counters(durable) == (0, 0)
    assert durable.app.state.job_queue.calls == []
    replay = create(durable)
    assert replay.json()["error_code"] == "UPLOAD_INCOMPLETE"


def test_timeout_fences_late_worker_before_releasing_and_retry_is_idempotent(durable, monkeypatch):
    queue = durable.app.state.job_queue
    queue.error = ConnectionError()
    job_id = create(durable).json()["id"]
    dispatch(durable, datetime.now(UTC) + timedelta(seconds=901))
    assert counters(durable) == (0, 0)
    factory = durable.app.state.session_factory
    assert not set_stage(factory, job_id, JobStatus.RUNNING, "preprocessing", expected_attempt=1)
    monkeypatch.setattr(
        "app.services.transcription.transcribe_audio",
        lambda *_args, **_kw: pytest.fail("fenced worker executed"),
    )
    run_service(durable, job_id)
    queue.error = None
    headers = {**OWNER, "Idempotency-Key": "retry-key-123"}
    first = durable.post(f"/jobs/{job_id}/retry", headers=headers)
    second = durable.post(f"/jobs/{job_id}/retry", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["attempt_count"] == second.json()["attempt_count"] == 2
    assert counters(durable) == (1, 0)
    assert queue.calls == [(job_id, 2)]


def test_deleted_submission_leaves_tombstone_and_never_recreates_task(durable):
    job_id = create(durable).json()["id"]
    assert durable.delete(f"/jobs/{job_id}", headers=OWNER).status_code == 204
    assert create(durable).status_code == 410
    dispatch(durable, datetime.now(UTC) + timedelta(seconds=31))
    with durable.app.state.session_factory() as session:
        assert session.get(TranscriptionJob, job_id) is None
        assert session.scalar(select(JobSubmission)) is not None
        assert session.scalar(select(JobDispatch)).status == "canceled"
    assert counters(durable) == (0, 0)


def test_pipeline_success_settles_once_and_monitor_does_not_reenqueue(durable, monkeypatch):
    job_id = create(durable).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    run_service(durable, job_id)
    dispatch(durable, datetime.now(UTC) + timedelta(seconds=40))
    assert counters(durable) == (0, 1)
    assert durable.app.state.job_queue.calls == [(job_id, 1)]


def test_lost_running_worker_is_fenced_and_released(durable):
    job_id = create(durable).json()["id"]
    factory = durable.app.state.session_factory
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert begin_dispatch_run(session, job, durable.app.state.settings)
    assert set_stage(factory, job_id, JobStatus.RUNNING, "transcribing", expected_attempt=1)
    dispatch(durable, datetime.now(UTC) + timedelta(seconds=961))
    assert counters(durable) == (0, 0)
    assert not set_stage(factory, job_id, JobStatus.RUNNING, "score", expected_attempt=1)


def test_cleanup_preserves_submission_and_ledger_history(durable):
    job_id = create(durable).json()["id"]
    result = cleanup_expired_jobs(
        durable.app.state.session_factory,
        durable.app.state.storage,
        durable.app.state.settings,
        now=datetime.now(UTC) + timedelta(days=2),
    )
    assert result.deleted == 1 and counters(durable) == (0, 0)
    assert create(durable).status_code == 410
    with durable.app.state.session_factory() as session:
        assert session.get(TranscriptionJob, job_id) is None
        assert session.scalar(select(JobSubmission)) is not None
        assert len(session.scalars(select(UsageLedger)).all()) == 2


def test_failure_result_can_be_replayed_after_http_response_loss(durable):
    job_id = create(durable).json()["id"]
    mark_failed(
        durable.app.state.session_factory,
        job_id,
        "NO_NOTES_DETECTED",
        "no notes",
        expected_attempt=1,
    )
    assert create(durable).json()["status"] == "failed"
    assert counters(durable) == (0, 0)


def test_turning_off_new_admissions_does_not_forget_existing_submission_keys(durable):
    first = create(durable)
    durable.app.state.settings.reliable_queue_enabled = False
    repeated = create(durable)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]
    assert len(durable.app.state.job_queue.calls) == 1


def test_retry_publish_failure_keeps_recoverable_attempt_and_one_reservation(durable):
    job_id = create(durable).json()["id"]
    mark_failed(
        durable.app.state.session_factory, job_id, "NO_NOTES", "no notes", expected_attempt=1
    )
    durable.app.state.job_quota.complete(job_id)
    durable.app.state.job_queue.error = ConnectionError("redis unavailable")
    headers = {**OWNER, "Idempotency-Key": "lost-retry-key"}
    response = durable.post(f"/jobs/{job_id}/retry", headers=headers)
    assert response.status_code == 200 and response.json()["attempt_count"] == 2
    assert durable.post(f"/jobs/{job_id}/retry", headers=headers).json()["attempt_count"] == 2
    assert counters(durable) == (1, 0)
    durable.app.state.job_queue.error = None
    dispatch(durable, datetime.now(UTC) + timedelta(seconds=40))
    assert durable.app.state.job_queue.calls == [(job_id, 1), (job_id, 2)]


def test_late_callback_never_releases_new_attempt_capacity(durable, monkeypatch):
    from app.jobs import tasks

    job_id = create(durable).json()["id"]
    factory = durable.app.state.session_factory
    mark_failed(factory, job_id, "NO_NOTES", "no notes", expected_attempt=1)
    durable.app.state.job_quota.complete(job_id)
    assert (
        durable.post(
            f"/jobs/{job_id}/retry", headers={**OWNER, "Idempotency-Key": "next-try-key"}
        ).status_code
        == 200
    )
    calls = []
    monkeypatch.setattr(tasks, "_complete_quota", lambda *_: calls.append(1))
    tasks._complete_attempt_quota(factory, durable.app.state.settings, job_id, 1)
    assert calls == []
    with factory() as session:
        tasks._fail_job(session, job_id, "WORKER_FAILED", "late", attempt=1)
    assert counters(durable) == (1, 0)


def test_expired_managed_job_cannot_start_a_worker(durable):
    job_id = create(durable).json()["id"]
    with durable.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        assert not begin_dispatch_run(session, job, durable.app.state.settings)


@pytest.mark.parametrize("guest", [True, False])
def test_new_requests_are_limited_before_expensive_audio_probe(durable, monkeypatch, guest):
    from app.services import durable_jobs

    durable.app.state.settings.hourly_job_limit = 1
    if guest:
        first = durable.post(
            "/jobs",
            files={"audio_file": ("audio.wav", wav_bytes(), "audio/wav")},
            data={"start_sec": 0, "end_sec": 2, "rights_confirmed": True},
        )
    else:
        first = create(durable)
    assert first.status_code == 201
    monkeypatch.setattr(
        durable_jobs, "validate_audio_file", lambda *_: pytest.fail("quota must precede probe")
    )
    if guest:
        second = durable.post(
            "/jobs",
            files={"audio_file": ("audio.wav", wav_bytes(), "audio/wav")},
            data={"start_sec": 0, "end_sec": 2, "rights_confirmed": True},
        )
    else:
        second = create(durable, key="new-key-123")
    assert second.status_code == 429


def test_duplicate_worker_delivery_does_not_execute_twice(durable, monkeypatch):
    from app.jobs import tasks

    job_id = create(durable).json()["id"]
    entered, release = Event(), Event()
    calls = []
    monkeypatch.setattr(tasks, "get_current_job", lambda: None)
    monkeypatch.setattr(tasks, "get_settings", lambda: durable.app.state.settings)

    def held_pipeline(*_args, **_kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(tasks, "run_transcription_job", held_pipeline)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(tasks.verify_source_job, job_id, 1)
        try:
            assert entered.wait(10)
            pool.submit(tasks.verify_source_job, job_id, 1).result(timeout=10)
            assert calls == [1]
        finally:
            release.set()
        first.result(timeout=10)
    assert counters(durable) == (1, 0)


def test_failed_dispatch_item_does_not_stop_other_pending_tasks(durable, monkeypatch):
    from app.services import dispatch as service

    first = create(durable).json()["id"]
    second = create(durable, token="bob").json()["id"]
    real = service.dispatch_one

    def one_fails(*args, **kwargs):
        if args[1] == first:
            raise OSError("single record failed")
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "dispatch_one", one_fails)
    assert dispatch(durable, datetime.now(UTC) + timedelta(seconds=40)) == 1
    assert (second, 1) in durable.app.state.job_queue.calls

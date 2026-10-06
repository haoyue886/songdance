"""Opt-in outbox races against disposable PostgreSQL; identity and queue stay offline."""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from app.main import create_app
from app.models import (
    JobDispatch,
    JobStatus,
    JobSubmission,
    TranscriptionJob,
    UsageLedger,
    UsagePeriod,
)
from app.services.dispatch import dispatch_one, dispatch_pending
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from app.services.transcription_persistence import mark_failed
from tests.conftest import RecordingQueue, wav_bytes
from tests.test_auth_ownership import FakeVerifier, auth_settings
from tests.test_auth_real_services import postgres  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; existing databases are never used",
)
API_ROOT = Path(__file__).resolve().parents[1]


def migrate(url, *args):
    subprocess.run(
        [str(API_ROOT / ".venv/bin/alembic"), *args],
        cwd=API_ROOT,
        env={**os.environ, "SONGDANCE_DATABASE_URL": url, "SONGDANCE_AUTH_ENABLED": "false"},
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def database(postgres):  # noqa: F811
    admin, _ = postgres
    name = "dispatch_test_" + uuid4().hex
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = admin.rsplit("/", 1)[0] + "/" + name
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://"))
    try:
        migrate(url, "upgrade", "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "010"
        yield url, engine, sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
def client(database, tmp_path):
    url, _, _ = database
    settings = auth_settings(tmp_path).model_copy(
        update={
            "database_url": url.replace("postgresql://", "postgresql+psycopg://"),
            "auto_create_schema": False,
            "reliable_queue_enabled": True,
            "usage_enabled": True,
            "hourly_job_limit": 1000,
            "daily_job_limit": 1000,
            "client_active_job_limit": 1000,
            "global_active_job_limit": 1000,
        }
    )
    app = create_app(
        settings,
        LocalObjectStorage(settings.local_storage_path),
        RecordingQueue(),
        MemoryJobQuota(settings),
    )
    verifier = app.state.auth_verifier
    app.state.auth_verifier = FakeVerifier({"alice": str(uuid4()), "bob": str(uuid4())})
    try:
        with TestClient(app) as test_client:
            for who in ("alice", "bob"):
                assert test_client.get("/me", headers=headers(who)).status_code == 200
            yield test_client
    finally:
        app.state.engine.dispose()
        verifier.engine.dispose()


def headers(who="alice", key="submission_key"):
    return {"Authorization": f"Bearer {who}", "Idempotency-Key": key}


def submit(client, who="alice", key="submission_key", end_sec="2"):
    return client.post(
        "/jobs",
        headers=headers(who, key),
        files={"audio_file": ("sample.wav", wav_bytes(), "audio/wav")},
        data={"start_sec": "0", "end_sec": end_sec, "rights_confirmed": "true"},
    )


def dispatch(state, job_id, attempt=1, **kwargs):
    return dispatch_one(
        state.session_factory,
        job_id,
        attempt,
        state.settings,
        state.job_queue,
        state.storage,
        state.job_quota,
        **kwargs,
    )


def pending_job(client):
    state = client.app.state
    state.job_queue.error = OSError("offline queue")
    response = submit(client)
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]
    state.job_queue.error = None
    with state.session_factory.begin() as session:
        row = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    return job_id


def ledger_events(session, reservation_id):
    return session.scalars(
        select(UsageLedger.event_type).where(UsageLedger.reservation_id == reservation_id)
    ).all()


def test_concurrent_same_key_posts_create_one_job_dispatch_and_reservation(client, monkeypatch):
    import app.services.durable_jobs as durable

    barrier = Barrier(2)
    replay = durable.replay_submission

    def synchronized_replay(*args, **kwargs):
        barrier.wait(timeout=15)
        return replay(*args, **kwargs)

    monkeypatch.setattr(durable, "replay_submission", synchronized_replay)

    def post(_):
        # Separate portals let both async request handlers reach the database concurrently.
        with TestClient(client.app) as parallel_client:
            return submit(parallel_client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(post, range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    state = client.app.state
    with state.session_factory() as session:
        assert len(session.scalars(select(TranscriptionJob)).all()) == 1
        assert len(session.scalars(select(JobSubmission)).all()) == 1
        assert len(session.scalars(select(JobDispatch)).all()) == 1
        rows = session.scalars(select(UsageLedger)).all()
        assert len(rows) == 1 and rows[0].event_type == "reservation"
        period = session.get(UsagePeriod, rows[0].period_id)
        assert (period.reserved_units, period.consumed_units) == (rows[0].units, 0)
    assert state.job_queue.calls == [(responses[0].json()["id"], 1)]


def test_same_key_is_account_scoped_and_changed_fingerprint_conflicts(client):
    alice, bob = submit(client), submit(client, "bob")
    assert (alice.status_code, bob.status_code) == (201, 201)
    assert alice.json()["id"] != bob.json()["id"]
    conflict = submit(client, end_sec="1")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(TranscriptionJob)).all()) == 2
        assert len(session.scalars(select(JobSubmission)).all()) == 2
        assert len(session.scalars(select(JobDispatch)).all()) == 2
        rows = session.scalars(select(UsageLedger)).all()
        assert len(rows) == 2 and all(row.event_type == "reservation" for row in rows)


def test_competing_dispatchers_lock_one_pending_outbox_before_publishing(client, monkeypatch):
    job_id = pending_job(client)
    state = client.app.state
    barrier = Barrier(2)
    enqueue_calls = []
    original = state.job_queue.enqueue_unique

    def enqueue(*args):
        enqueue_calls.append(args)
        return original(*args)

    def synchronize_candidates(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT job_dispatches.job_id, job_dispatches.attempt"):
            barrier.wait(timeout=15)

    monkeypatch.setattr(state.job_queue, "enqueue_unique", enqueue)
    event.listen(state.engine, "after_cursor_execute", synchronize_candidates)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: dispatch_pending(
                        state.session_factory,
                        state.settings,
                        state.job_queue,
                        state.storage,
                        state.job_quota,
                    ),
                    range(2),
                )
            )
    finally:
        event.remove(state.engine, "after_cursor_execute", synchronize_candidates)
    assert sum(results) == 1
    assert enqueue_calls == [(job_id, 1)]
    assert state.job_queue.calls == [(job_id, 1)]
    with state.session_factory() as session:
        row = session.scalar(select(JobDispatch))
        assert (row.status, row.publish_attempts) == ("published", 2)


def observe_job_lock(engine, reached):
    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT transcription_jobs.") and "FOR UPDATE" in statement:
            reached.set()

    event.listen(engine, "before_cursor_execute", observe)
    return observe


def test_delete_waits_for_publisher_then_cancels_outbox_and_releases_once(client, monkeypatch):
    job_id = pending_job(client)
    state = client.app.state
    entered, release, deleting = Event(), Event(), Event()
    original = state.job_queue.enqueue_unique

    def held_enqueue(*args):
        entered.set()
        assert release.wait(15), "publisher was not released"
        return original(*args)

    monkeypatch.setattr(state.job_queue, "enqueue_unique", held_enqueue)
    with ThreadPoolExecutor(max_workers=2) as pool:
        publishing = pool.submit(dispatch, state, job_id)
        assert entered.wait(15)
        listener = observe_job_lock(state.engine, deleting)
        try:
            deletion = pool.submit(client.delete, f"/jobs/{job_id}", headers=headers())
            assert deleting.wait(15)
            assert not deletion.done()
        finally:
            release.set()
            event.remove(state.engine, "before_cursor_execute", listener)
        assert publishing.result(timeout=15)
        assert deletion.result(timeout=15).status_code == 204
    assert dispatch(state, job_id, now=datetime.now(UTC) + timedelta(minutes=1))
    with state.session_factory() as session:
        assert session.get(TranscriptionJob, job_id) is None
        assert session.scalar(select(JobDispatch.status)) == "canceled"
        assert sorted(session.scalars(select(UsageLedger.event_type)).all()) == [
            "release",
            "reservation",
        ]
        period = session.scalar(select(UsagePeriod))
        assert (period.reserved_units, period.consumed_units) == (0, 0)
    assert job_id not in state.job_quota._jobs


def test_timeout_holds_job_lock_until_retry_can_reserve_new_attempt(client, monkeypatch):
    job_id = pending_job(client)
    state = client.app.state
    with state.session_factory.begin() as session:
        row = session.scalar(select(JobDispatch))
        row.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    entered, release, retrying = Event(), Event(), Event()
    original = state.job_quota.complete

    def held_complete(*args):
        entered.set()
        assert release.wait(15), "timeout settlement was not released"
        return original(*args)

    monkeypatch.setattr(state.job_quota, "complete", held_complete)
    with ThreadPoolExecutor(max_workers=2) as pool:
        timing_out = pool.submit(dispatch, state, job_id)
        assert entered.wait(15)
        listener = observe_job_lock(state.engine, retrying)
        try:
            retry = pool.submit(
                client.post, f"/jobs/{job_id}/retry", headers=headers(key="retry_key_2")
            )
            assert retrying.wait(15)
            assert not retry.done()
        finally:
            release.set()
            event.remove(state.engine, "before_cursor_execute", listener)
        assert timing_out.result(timeout=15)
        response = retry.result(timeout=15)
        assert response.status_code == 200, response.text
    with state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert (job.status, job.attempt_count) == (JobStatus.QUEUED, 2)
        assert ledger_events(session, job.usage_reservation_id) == ["reservation"]
        rows = session.scalars(select(JobDispatch).order_by(JobDispatch.attempt)).all()
        assert [(row.status, row.error_code) for row in rows] == [
            ("failed", "DISPATCH_TIMEOUT"),
            ("published", None),
        ]
        assert sorted(session.scalars(select(UsageLedger.event_type)).all()) == [
            "release",
            "reservation",
            "reservation",
        ]
    assert job_id in state.job_quota._jobs


def test_old_dispatch_waiting_on_retry_never_settles_new_attempt(client, monkeypatch):
    import app.routes.jobs as routes

    job_id = pending_job(client)
    state = client.app.state
    mark_failed(state.session_factory, job_id, "TEST_FAILED", "retryable", expected_attempt=1)
    entered, release, dispatching = Event(), Event(), Event()
    original = routes.add_dispatch

    def held_add(*args, **kwargs):
        original(*args, **kwargs)
        entered.set()
        assert release.wait(15), "retry was not released"

    monkeypatch.setattr(routes, "add_dispatch", held_add)
    with ThreadPoolExecutor(max_workers=2) as pool:
        retry = pool.submit(
            client.post, f"/jobs/{job_id}/retry", headers=headers(key="retry_key_2")
        )
        assert entered.wait(15)
        listener = observe_job_lock(state.engine, dispatching)
        try:
            stale = pool.submit(dispatch, state, job_id)
            assert dispatching.wait(15)
            assert not stale.done()
        finally:
            release.set()
            event.remove(state.engine, "before_cursor_execute", listener)
        assert retry.result(timeout=15).status_code == 200
        assert stale.result(timeout=15)
    with state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert (job.status, job.attempt_count) == (JobStatus.QUEUED, 2)
        assert ledger_events(session, job.usage_reservation_id) == ["reservation"]
        rows = session.scalars(select(JobDispatch).order_by(JobDispatch.attempt)).all()
        assert [row.status for row in rows] == ["canceled", "published"]
        period = session.scalar(select(UsagePeriod))
        assert (period.reserved_units, period.consumed_units) == (1, 0)
    assert state.job_queue.calls == [(job_id, 2)]
    assert job_id in state.job_quota._jobs


def test_010_postgres_migration_keeps_legacy_tasks_unmanaged(database):
    url, engine, factory = database
    migrate(url, "downgrade", "009")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO transcription_jobs "
                "(id,status,stage,source_type,start_sec,end_sec,attempt_count,expires_at) "
                "VALUES ('legacy','queued','queued','upload',0,15,1,now() + interval '1 day')"
            )
        )
    migrate(url, "upgrade", "head")
    with factory() as session:
        job = session.get(TranscriptionJob, "legacy")
        assert job.dispatch_managed is False
        assert (job.status, job.attempt_count, job.end_sec) == ("queued", 1, 15)
        assert session.scalars(select(JobDispatch)).all() == []
        assert session.scalars(select(JobSubmission)).all() == []


def test_execution_advisory_lock_blocks_duplicate_and_releases_after_exception(database, tmp_path):
    from app.services.execution_guard import execution_guard

    _, engine, _ = database
    settings = auth_settings(tmp_path)
    job_id = uuid4().hex
    with pytest.raises(RuntimeError):
        with execution_guard(engine, settings, job_id, 1) as acquired:
            assert acquired
            with execution_guard(engine, settings, job_id, 1) as duplicate:
                assert duplicate is False
            with execution_guard(engine, settings, job_id, 2) as other_attempt:
                assert other_attempt is True
            raise RuntimeError("pipeline interrupted")
    with execution_guard(engine, settings, job_id, 1) as retry:
        assert retry is True

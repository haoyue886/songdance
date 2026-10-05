from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.main import create_app
from app.models import Base, JobStatus, TranscriptionJob, UsageLedger, UsagePeriod, User
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from app.services.usage import (
    UsageExceeded,
    reserve_free,
    settle_job,
    settle_job_in_factory,
    utc_month,
)
from tests.conftest import RecordingQueue
from tests.test_auth_ownership import FakeVerifier, auth_settings, create_job


class FailingDeleteStorage:
    def __init__(self, delegate) -> None:
        self.delegate = delegate

    def delete(self, _key: str) -> None:
        raise OSError("object storage unavailable")


@pytest.fixture
def protected_client(tmp_path: Path):
    settings = auth_settings(tmp_path)
    app = create_app(
        settings,
        storage=LocalObjectStorage(settings.local_storage_path),
        job_queue=RecordingQueue(),
        job_quota=MemoryJobQuota(settings),
    )
    verifier = app.state.auth_verifier
    app.state.auth_verifier = FakeVerifier({"alice": str(uuid4()), "bob": str(uuid4())})
    with TestClient(app) as client:
        yield client
    app.state.engine.dispose()
    verifier.engine.dispose()


def usage_session(tmp_path: Path):
    settings = auth_settings(tmp_path).model_copy(update={"usage_enabled": True})
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return settings, engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_free_month_is_one_reservation_and_immutable_terminal_event(tmp_path: Path) -> None:
    settings, engine, factory = usage_session(tmp_path)
    try:
        user = User(id="11111111-1111-4111-8111-111111111111", email="free@example.test")
        with factory() as session:
            session.add(user)
            session.commit()
            first = reserve_free(session, user, "job-1", settings)
            session.add(
                TranscriptionJob(
                    id="job-1",
                    owner_user_id=user.id,
                    usage_reservation_id=first,
                    start_sec=0,
                    end_sec=1,
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                )
            )
            session.commit()
            with pytest.raises(UsageExceeded):
                reserve_free(session, user, "job-2", settings)
        # The reservation above is already persisted; failure returns the sole monthly slot.
        assert settle_job_in_factory(factory, "job-1", success=False) is True
        with factory() as session:
            period = session.scalar(select(UsagePeriod))
            assert period is not None
            assert (period.reserved_units, period.consumed_units) == (0, 0)
            assert {row.event_type for row in session.scalars(select(UsageLedger)).all()} == {
                "reservation",
                "release",
            }
            second = reserve_free(session, user, "job-3", settings)
            assert second != first
    finally:
        engine.dispose()


def test_free_success_consumes_once_and_repeated_settlement_is_idempotent(tmp_path: Path) -> None:
    settings, engine, factory = usage_session(tmp_path)
    try:
        user = User(id="22222222-2222-4222-8222-222222222222", email="free2@example.test")
        with factory() as session:
            session.add(user)
            session.commit()
            reservation = reserve_free(session, user, "job-2", settings)
            job = TranscriptionJob(
                id="job-2",
                owner_user_id=user.id,
                usage_reservation_id=reservation,
                start_sec=0,
                end_sec=1,
                expires_at=datetime.now(UTC),
            )
            session.add(job)
            session.commit()
        assert settle_job_in_factory(factory, "job-2", success=True) is True
        assert settle_job_in_factory(factory, "job-2", success=True) is False
        with factory() as session:
            period = session.scalar(select(UsagePeriod))
            assert period is not None and (period.reserved_units, period.consumed_units) == (0, 1)
            assert [
                row.event_type
                for row in session.scalars(
                    select(UsageLedger).order_by(UsageLedger.created_at)
                ).all()
            ] == ["reservation", "consume"]
    finally:
        engine.dispose()


def test_settlement_fences_late_worker_attempt_and_reservation(tmp_path: Path) -> None:
    settings, engine, factory = usage_session(tmp_path)
    settings.free_monthly_job_limit = 2
    try:
        user = User(id="33333333-3333-4333-8333-333333333333", email="fence@example.test")
        with factory() as session:
            session.add(user)
            session.commit()
            first = reserve_free(session, user, "job-fence", settings)
            job = TranscriptionJob(
                id="job-fence",
                owner_user_id=user.id,
                usage_reservation_id=first,
                attempt_count=1,
                start_sec=0,
                end_sec=1,
                expires_at=datetime.now(UTC),
            )
            session.add(job)
            session.commit()
            second = reserve_free(session, user, "job-fence", settings)
            job.attempt_count = 2
            job.usage_reservation_id = second
            session.commit()

        assert (
            settle_job_in_factory(
                factory,
                "job-fence",
                success=True,
                expected_attempt=1,
                reservation_id=first,
            )
            is False
        )
        with factory() as session:
            period = session.scalar(select(UsagePeriod))
            assert period is not None and (period.reserved_units, period.consumed_units) == (2, 0)
            assert [
                row.event_type
                for row in session.scalars(select(UsageLedger)).all()
            ] == ["reservation", "reservation"]
    finally:
        engine.dispose()


def test_utc_month_boundaries_are_explicit() -> None:
    january = utc_month(datetime(2026, 1, 31, 23, 59, tzinfo=UTC))
    february = utc_month(datetime(2026, 2, 1, 0, 0, tzinfo=UTC))
    assert january[0] == "free:2026-01" and january[2] == february[1]
    assert february[0] == "free:2026-02"


def test_authenticated_usage_enabled_endpoint_blocks_second_success(protected_client) -> None:
    client = protected_client
    client.app.state.settings.usage_enabled = True
    first = create_job(client, "alice")
    assert first.status_code == 201
    job_id = first.json()["id"]
    assert (
        client.post(f"/jobs/{job_id}/retry", headers={"Authorization": "Bearer alice"}).status_code
        == 409
    )
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        assert settle_job(session, job, success=True) is True
    second = create_job(client, "alice")
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "FREE_MONTHLY_LIMIT"


def test_retry_queue_failure_releases_new_free_reservation(protected_client) -> None:
    client = protected_client
    client.app.state.settings.usage_enabled = True
    created = create_job(client, "alice")
    assert created.status_code == 201
    job_id = created.json()["id"]
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        job.status = JobStatus.FAILED
        job.error_code = "WORKER_FAILED"
        job.error_message = "worker failed"
        assert settle_job(session, job, success=False) is True
    client.app.state.job_quota.complete(job_id)
    client.app.state.job_queue.error = RuntimeError("redis offline")

    response = client.post(f"/jobs/{job_id}/retry", headers={"Authorization": "Bearer alice"})

    assert response.status_code == 503
    with client.app.state.session_factory() as session:
        period = session.scalar(select(UsagePeriod))
        assert period is not None
        assert (period.reserved_units, period.consumed_units) == (0, 0)
        events = session.scalars(select(UsageLedger)).all()
        assert len(events) == 4
        assert {row.event_type for row in events} == {"reservation", "release"}
        reservation_ids = {row.reservation_id for row in events}
        assert len(reservation_ids) == 2
        assert {(row.reservation_id, row.event_type) for row in events} == {
            (reservation_id, event_type)
            for reservation_id in reservation_ids
            for event_type in ("reservation", "release")
        }


def test_delete_failure_releases_free_reservation(protected_client) -> None:
    client = protected_client
    client.app.state.settings.usage_enabled = True
    created = create_job(client, "alice")
    assert created.status_code == 201
    job_id = created.json()["id"]
    client.app.state.storage = FailingDeleteStorage(client.app.state.storage)

    response = client.delete(f"/jobs/{job_id}", headers={"Authorization": "Bearer alice"})

    assert response.status_code == 503
    with client.app.state.session_factory() as session:
        period = session.scalar(select(UsagePeriod))
        job = session.get(TranscriptionJob, job_id)
        assert period is not None and (period.reserved_units, period.consumed_units) == (0, 0)
        assert job is not None and job.error_code == "DELETE_FAILED"
        releases = session.scalars(
            select(UsageLedger).where(UsageLedger.event_type == "release")
        ).all()
        assert len(releases) == 1 and releases[0].details == '{"source":"delete_failed"}'

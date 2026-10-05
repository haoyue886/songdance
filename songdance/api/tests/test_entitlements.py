from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.jobs.cleanup import cleanup_expired_jobs
from app.models import JobStatus, TranscriptionJob, UsageLedger, UsagePeriod, User
from app.services.entitlements import charge_seconds, reserve_job
from app.services.paid_periods import grant_paid_period, set_paid_period_status
from app.services.quota import MemoryJobQuota, QuotaExceeded
from app.services.transcription_persistence import (
    ArtifactOutcome,
    mark_failed,
    persist_artifact_outcomes,
)
from app.services.usage import UsageExceeded, reserve_free, reserve_period, settle_job
from app.settings import Settings
from tests.test_auth_ownership import create_job
from tests.test_usage_ledger import protected_client as protected_client
from tests.test_usage_ledger import usage_session
from tests.transcription_helpers import fake_transcription, run_service


def grant(session, user_id, **overrides):
    now = datetime.now(UTC)
    facts = dict(
        user_id=user_id,
        environment="test",
        transaction_id="tx-1",
        subscription_id="sub-1",
        product_id="test-product",
        plan_version="test-v1",
        amount_minor=990,
        currency="USD",
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=29),
        limit_seconds=1800,
        max_clip_seconds=90,
    )
    facts.update(overrides)
    return grant_paid_period(session, **facts)


def enable_paid(client, **overrides):
    settings = client.app.state.settings
    settings.usage_enabled = settings.paid_usage_enabled = True
    user_id = client.get("/me", headers={"Authorization": "Bearer alice"}).json()["id"]
    with client.app.state.session_factory() as session:
        paid = grant(session, user_id, **overrides)
        session.commit()
        return paid


@pytest.mark.parametrize("duration,seconds", [(1, 15), (14.9, 15), (15, 15), (30.1, 31), (90, 90)])
def test_metering(duration, seconds):
    assert charge_seconds(duration) == seconds


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1, 0, True])
def test_metering_rejects_nonfinite_or_invalid(duration):
    with pytest.raises(ValueError):
        charge_seconds(duration)


def test_paid_admission_summary_is_private_and_never_falls_back(protected_client):
    client = protected_client
    paid = enable_paid(client, limit_seconds=20)
    first = create_job(client, "alice")
    assert first.status_code == 201
    alice = {"Authorization": "Bearer alice"}
    summary = client.get("/billing/me", headers=alice)
    assert summary.headers["cache-control"] == "private, no-store"
    assert summary.json()["plan"] == "pro"
    assert summary.json()["reserved"] == 15 and summary.json()["remaining"] == 5
    assert create_job(client, "alice").json()["detail"]["code"] == "QUOTA_EXCEEDED"
    assert client.get("/billing/me").status_code == 401
    other = client.get("/billing/me", headers={"Authorization": "Bearer bob"}).json()
    assert other["plan"] == "free" and other["remaining"] == 1
    with client.app.state.session_factory() as session:
        assert (
            session.scalar(
                select(UsagePeriod).where(
                    UsagePeriod.user_id == paid.user_id,
                    UsagePeriod.entitlement_type == "free_month",
                )
            )
            is None
        )


@pytest.mark.parametrize("state", ["frozen", "revoked"])
def test_suspended_paid_period_does_not_spend_free(protected_client, state):
    client = protected_client
    paid = enable_paid(client)
    with client.app.state.session_factory() as session:
        set_paid_period_status(
            session,
            user_id=paid.user_id,
            environment="test",
            transaction_id=paid.transaction_id,
            status=state,
        )
        session.commit()
    assert create_job(client, "alice").json()["detail"]["code"] == "ENTITLEMENT_SUSPENDED"
    with client.app.state.session_factory() as session:
        assert not session.scalars(select(UsageLedger)).all()


def test_paid_environment_isolation_and_current_clip_cap(protected_client):
    client = protected_client
    enable_paid(client, environment="live")
    assert create_job(client, "alice").status_code == 201
    summary = client.get("/billing/me", headers={"Authorization": "Bearer alice"}).json()
    assert summary["plan"] == "free"
    with client.app.state.session_factory() as session:
        user = session.get(
            User, client.get("/me", headers={"Authorization": "Bearer bob"}).json()["id"]
        )
        grant(session, user.id, transaction_id="b", subscription_id="b")
        session.commit()
        with pytest.raises(HTTPException) as error:
            reserve_job(session, user, "long", client.app.state.settings, duration=91)
        assert error.value.status_code == 422


def test_release_then_late_success_cannot_steal_another_reservation(tmp_path):
    settings, engine, factory = usage_session(tmp_path)
    try:
        with factory() as session:
            user = User(id="terminal-owner")
            session.add(user)
            session.commit()
            first = reserve_free(session, user, "a", settings)
            job = TranscriptionJob(
                id="a",
                usage_reservation_id=first,
                start_sec=0,
                end_sec=2,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            session.add(job)
            session.commit()
            assert settle_job(session, job, success=False)
            session.commit()
            reserve_free(session, user, "b", settings)
            session.commit()
            assert not settle_job(session, job, success=True)
            session.commit()
            period = session.scalar(select(UsagePeriod))
            assert (period.reserved_units, period.consumed_units) == (1, 0)
            session.add(
                UsageLedger(
                    id="forged",
                    period_id=period.id,
                    user_id=user.id,
                    job_id="a",
                    reservation_id=first,
                    event_type="consume",
                    units=1,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        engine.dispose()


def test_twenty_seconds_cannot_accept_two_fifteen_second_reservations(tmp_path):
    settings, engine, factory = usage_session(tmp_path)
    try:
        with factory() as session:
            user = User(id="concurrent-owner")
            session.add(user)
            session.commit()
            paid = grant(session, user.id, limit_seconds=20)
            session.commit()
            period_id = paid.usage_period_id
        barrier = Barrier(2)

        def attempt(index):
            with factory() as session:
                period = session.get(UsagePeriod, period_id)
                barrier.wait(timeout=10)
                try:
                    reserve_period(session, period, f"job-{index}", 15)
                    session.commit()
                    return True
                except UsageExceeded:
                    session.rollback()
                    return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(attempt, range(2))) == [False, True]
        with factory() as session:
            period = session.get(UsagePeriod, period_id)
            assert (period.reserved_units, period.consumed_units) == (15, 0)
    finally:
        engine.dispose()


def test_pipeline_success_and_cleanup_keep_consumption(protected_client, monkeypatch):
    client = protected_client
    paid = enable_paid(client)
    job_id = create_job(client, "alice").json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(
        "app.services.transcription_artifacts.write_musicxml",
        lambda *_: (_ for _ in ()).throw(RuntimeError("xml failed")),
    )
    run_service(client, job_id)
    factory = client.app.state.session_factory
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job.status == JobStatus.SUCCEEDED
        period = session.get(UsagePeriod, paid.usage_period_id)
        assert (period.reserved_units, period.consumed_units) == (0, 15)
    # A duplicate delivery cannot rerun the model or clear already delivered artifacts.
    monkeypatch.setattr(
        "app.services.transcription.transcribe_audio",
        lambda *_args, **_kw: pytest.fail("duplicate execution"),
    )
    run_service(client, job_id)
    result = cleanup_expired_jobs(
        factory,
        client.app.state.storage,
        client.app.state.settings,
        now=datetime.now(UTC) + timedelta(days=2),
    )
    assert result.deleted == 1
    with factory() as session:
        assert session.get(TranscriptionJob, job_id) is None
        assert session.get(UsagePeriod, paid.usage_period_id).consumed_units == 15
        assert len(session.scalars(select(UsageLedger)).all()) == 2


def test_failure_settlement_rolls_back_with_job_and_retry_releases(protected_client, monkeypatch):
    client = protected_client
    paid = enable_paid(client)
    job_id = create_job(client, "alice").json()["id"]
    factory = client.app.state.session_factory
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        job.status = JobStatus.FAILED
        settle_job(session, job, success=False)
        session.rollback()
    with factory() as session:
        assert session.get(TranscriptionJob, job_id).status == JobStatus.QUEUED
        assert session.get(UsagePeriod, paid.usage_period_id).reserved_units == 15
    mark_failed(factory, job_id, "NO_NOTES", "no notes", expected_attempt=1)
    client.app.state.job_quota.complete(job_id)
    assert (
        client.post(f"/jobs/{job_id}/retry", headers={"Authorization": "Bearer alice"}).status_code
        == 200
    )
    with factory() as session:
        period = session.get(UsagePeriod, paid.usage_period_id)
        assert (period.reserved_units, period.consumed_units) == (15, 0)
        assert len(session.scalars(select(UsageLedger)).all()) == 3


def test_expiry_returns_existing_free_month_without_moving_old_charge(protected_client):
    client = protected_client
    now = datetime.now(UTC)
    paid = enable_paid(
        client, period_start=now - timedelta(days=32), period_end=now - timedelta(seconds=1)
    )
    factory = client.app.state.session_factory
    with factory() as session:
        period = session.get(UsagePeriod, paid.usage_period_id)
        old = reserve_period(session, period, "old-job", 15)
        job = TranscriptionJob(
            id="old-job",
            usage_reservation_id=old,
            owner_user_id=paid.user_id,
            start_sec=0,
            end_sec=2,
            status=JobStatus.SUCCEEDED,
            expires_at=now + timedelta(hours=1),
        )
        session.add(job)
        session.commit()
        settle_job(session, job, success=True)
        session.commit()
    assert create_job(client, "alice").status_code == 201
    with factory() as session:
        assert session.get(UsagePeriod, paid.usage_period_id).consumed_units == 15
        free = session.scalar(
            select(UsagePeriod).where(UsagePeriod.entitlement_type == "free_month")
        )
        assert free.limit_units == 1 and free.reserved_units == 1 and free.consumed_units == 0


def test_pro_quota_separates_free_ip_budget_and_preserves_security_limits():
    settings = Settings(
        _env_file=None,
        quota_backend="memory",
        hourly_job_limit=1,
        client_active_job_limit=1,
        global_active_job_limit=8,
        paid_ip_hourly_job_limit=3,
    )
    quota = MemoryJobQuota(settings)
    quota.reserve("free", "shared-ip")
    for index in range(3):
        quota.reserve(f"paid-{index}", "shared-ip", paid=True)
    with pytest.raises(QuotaExceeded) as error:
        quota.reserve("too-many", "shared-ip", paid=True)
    assert error.value.code == "IP_SECURITY_LIMIT"
    with pytest.raises(QuotaExceeded) as error:
        quota.reserve("free-blocked", "shared-ip")
    assert error.value.code == "HOURLY_LIMIT"
    quota.cancel("paid-0")
    quota.reserve("replacement", "shared-ip", paid=True)


def test_paid_route_does_not_take_free_quota_path(protected_client):
    client = protected_client
    settings = client.app.state.settings
    settings.hourly_job_limit = settings.client_active_job_limit = 1
    enable_paid(client)
    client.app.state.job_quota.reserve("other-free-user", "unused")
    for _ in range(4):
        response = create_job(client, "alice")
        assert response.status_code == 201
        assert (
            client.delete(
                f"/jobs/{response.json()['id']}", headers={"Authorization": "Bearer alice"}
            ).status_code
            == 204
        )


def test_invalid_midi_fails_without_consuming(protected_client, monkeypatch):
    client = protected_client
    paid = enable_paid(client)
    job_id = create_job(client, "alice").json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(
        "app.services.transcription_artifacts.write_quantized_midi",
        lambda _scored, path: path.write_bytes(b"not a valid MIDI"),
    )
    run_service(client, job_id)
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        period = session.get(UsagePeriod, paid.usage_period_id)
        assert job.status == JobStatus.FAILED
        assert job.error_code == "MIDI_VALIDATION_FAILED"
        assert (period.reserved_units, period.consumed_units) == (0, 0)


def test_metered_youtube_cannot_bypass_ledger(protected_client):
    client = protected_client
    client.app.state.settings.usage_enabled = True
    client.app.state.settings.youtube_enabled = True
    assert client.get("/youtube/config").json()["enabled"] is False
    response = client.post(
        "/youtube/jobs",
        headers={"Authorization": "Bearer alice"},
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "start_sec": 0,
            "end_sec": 2,
            "rights_confirmed": True,
        },
    )
    assert response.status_code == 503


def test_current_account_allows_only_one_active_pro_task(protected_client):
    client = protected_client
    paid = enable_paid(client)
    assert create_job(client, "alice").status_code == 201
    response = create_job(client, "alice")
    assert response.status_code == 429 and response.json()["detail"]["code"] == "ACTIVE_JOB_EXISTS"
    with client.app.state.session_factory() as session:
        assert session.get(UsagePeriod, paid.usage_period_id).reserved_units == 15


def test_late_same_attempt_outcome_cannot_delete_published_midi(protected_client, monkeypatch):
    client = protected_client
    enable_paid(client)
    job_id = create_job(client, "alice").json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    run_service(client, job_id)
    factory = client.app.state.session_factory
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        midi = next(item for item in job.artifacts if item.type == "midi")
        outcome = ArtifactOutcome(
            "midi", midi.status, midi.storage_key, midi.mime_type, midi.size_bytes, midi.error_code
        )
    storage = client.app.state.storage
    assert not persist_artifact_outcomes(factory, storage, job_id, [outcome], expected_attempt=1)
    response = client.get(
        f"/jobs/{job_id}/download-url/midi", headers={"Authorization": "Bearer alice"}
    )
    assert response.status_code == 200
    assert client.get(response.json()["path"]).status_code == 200


def test_empty_and_unconfigured_usage_and_environment_gate(protected_client):
    client = protected_client
    headers = {"Authorization": "Bearer alice"}
    assert client.get("/billing/me", headers=headers).json() == {"enabled": False, "plan": None}
    client.app.state.settings.usage_enabled = True
    first = client.get("/billing/me", headers=headers).json()
    assert first["remaining"] == 1 and first["unit"] == "jobs"
    assert first["period_start"].endswith("Z")
    with pytest.raises(ValueError, match="Paid usage requires"):
        Settings(_env_file=None, paid_usage_enabled=True)

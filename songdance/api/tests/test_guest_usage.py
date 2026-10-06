from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select

from app.jobs.cleanup import cleanup_expired_jobs
from app.models import (
    GuestDay,
    GuestLedger,
    GuestSubmission,
    GuestTrial,
    JobDispatch,
    TranscriptionJob,
    UsageLedger,
)
from app.services.dispatch import dispatch_pending
from app.services.guest_usage import reserve_guest_day, visitor_id
from app.services.transcription_persistence import mark_failed
from app.services.usage import settle_job_in_factory
from tests.conftest import wav_bytes
from tests.test_usage_ledger import protected_client as protected_client
from tests.transcription_helpers import fake_transcription, run_service


@pytest.fixture
def guest_client(protected_client):
    settings = protected_client.app.state.settings
    settings.reliable_queue_enabled = True
    settings.usage_enabled = True
    settings.guest_usage_enabled = True
    settings.guest_signing_secret = SecretStr("guest-test-secret-at-least-thirty-two-characters")
    return protected_client


def visitor(client, token=None, origin=None):
    headers = {"Origin": origin or client.app.state.settings.cors_origin_list[0]}
    if token is not None:
        headers["X-Visitor-Token"] = token
    return client.post("/guest/session", headers=headers)


def submit(client, token, key="guest-create-key", *, content=None, **values):
    return client.post(
        "/jobs",
        headers={"X-Visitor-Token": token, "Idempotency-Key": key},
        files={"audio_file": ("sample.wav", content or wav_bytes(), "audio/wav")},
        data={"start_sec": "0", "end_sec": "2", "rights_confirmed": "true", **values},
    )


def access(job, key="guest-retry-key"):
    return {"X-Job-Access": job["guest_access_token"], "Idempotency-Key": key}


def counters(client, token):
    identity = visitor_id(client.app.state.settings, token)
    with client.app.state.session_factory() as session:
        trial = session.get(GuestTrial, identity)
        return (trial.reserved, trial.consumed) if trial else (0, 0)


def fail(client, job):
    mark_failed(
        client.app.state.session_factory,
        job["id"],
        "NO_NOTES_DETECTED",
        "no notes",
        expected_attempt=job["attempt_count"],
    )
    client.app.state.job_quota.complete(job["id"])


def dispatch(client, **kwargs):
    state = client.app.state
    return dispatch_pending(
        state.session_factory,
        state.settings,
        state.job_queue,
        state.storage,
        state.job_quota,
        **kwargs,
    )


def test_session_is_origin_restricted_signed_and_not_cacheable(guest_client):
    client = guest_client
    assert client.post("/guest/session").status_code == 403
    assert visitor(client, origin="https://untrusted.example").status_code == 403
    first = visitor(client)
    assert first.status_code == 200 and first.headers["cache-control"] == "private, no-store"
    token = first.json()["visitor_token"]
    assert first.json() == {
        "visitor_token": token,
        "remaining": 1,
        "reserved": 0,
        "used": 0,
        "max_clip_seconds": 30,
    }
    assert visitor(client, token).json() == first.json()
    assert visitor(client).json()["visitor_token"] != token
    forged = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert visitor(client, forged).json()["detail"]["code"] == "VISITOR_INVALID"
    assert visitor(client, "not-signed").json()["detail"]["code"] == "VISITOR_REQUIRED"
    client.app.state.settings.guest_usage_enabled = False
    assert visitor(client, token).status_code == 503


def test_create_requires_visitor_and_idempotency_key(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    assert submit(client, "invalid").status_code == 401
    assert submit(client, token, key="").status_code == 422
    assert counters(client, token) == (0, 0)
    assert client.app.state.job_queue.calls == []


def test_create_replay_preserves_capability_and_single_durable_admission(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    first = submit(client, token)
    assert first.status_code == 201
    job = first.json()
    client.app.state.settings.hourly_job_limit = 1
    replay = submit(client, token)
    assert replay.status_code == 201
    assert replay.json()["id"] == job["id"]
    assert replay.json()["guest_access_token"] == job["guest_access_token"]
    assert client.get(f"/jobs/{job['id']}").status_code == 404
    assert client.get(f"/jobs/{job['id']}", headers=access(job)).status_code == 200
    assert counters(client, token) == (1, 0)
    assert visitor(client, token).json()["remaining"] == 0
    with client.app.state.session_factory() as session:
        for model in (GuestDay, GuestLedger, GuestSubmission, JobDispatch, TranscriptionJob):
            assert len(session.scalars(select(model)).all()) == 1
        persisted = session.get(TranscriptionJob, job["id"])
        assert persisted.guest_secret_hash != job["guest_access_token"]
        assert persisted.usage_reservation_id is None
    assert client.app.state.job_queue.calls == [(job["id"], 1)]


def test_same_key_conflicts_and_new_identity_cannot_bypass_ip_day(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    assert submit(client, token).status_code == 201
    assert submit(client, token, end_sec="1").json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert submit(client, token, content=wav_bytes(frequency=440)).status_code == 409
    assert submit(client, token, key="new-create-key").json()["detail"]["code"] == (
        "GUEST_TRIAL_ACTIVE"
    )
    other = visitor(client).json()["visitor_token"]
    blocked = submit(client, other)
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "GUEST_DAILY_LIMIT"
    assert int(blocked.headers["retry-after"]) >= 1
    assert counters(client, other) == (0, 0)


@pytest.mark.parametrize("invalid", ["audio", "clip"])
def test_invalid_input_rolls_back_trial_and_daily_admission(guest_client, invalid):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    response = (
        submit(client, token, content=b"invalid audio")
        if invalid == "audio"
        else submit(client, token, end_sec="31")
    )
    assert response.status_code == 422
    assert counters(client, token) == (0, 0)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(GuestDay)) is None
        assert session.scalar(select(GuestLedger)) is None
    assert submit(client, token).status_code == 201


def test_failed_attempt_retries_without_new_ip_admission_or_account_charge(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    fail(client, job)
    assert counters(client, token) == (0, 0)
    assert visitor(client, token).json()["remaining"] == 1
    assert submit(client, token, key="another-create").json()["detail"]["code"] == (
        "GUEST_DAILY_LIMIT"
    )
    first = client.post(f"/jobs/{job['id']}/retry", headers=access(job))
    replay = client.post(f"/jobs/{job['id']}/retry", headers=access(job))
    assert first.status_code == replay.status_code == 200
    assert first.json()["attempt_count"] == replay.json()["attempt_count"] == 2
    assert counters(client, token) == (1, 0)
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(GuestDay)).all()) == 1
        assert len(session.scalars(select(GuestLedger)).all()) == 3
        assert session.scalar(select(UsageLedger)) is None
    assert client.app.state.job_queue.calls == [(job["id"], 1), (job["id"], 2)]


def test_retry_requires_capability_and_new_operation_key(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    fail(client, job)
    path = f"/jobs/{job['id']}/retry"
    assert client.post(path, headers={"X-Visitor-Token": token}).status_code == 404
    assert client.post(path, headers={"X-Job-Access": job["guest_access_token"]}).status_code == 422
    assert client.post(path, headers=access(job, "guest-create-key")).status_code == 409
    assert counters(client, token) == (0, 0)


def test_claimed_guest_retry_preserves_trial_and_invalidates_guest_access(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    fail(client, job)
    owner = {"Authorization": "Bearer alice"}
    claimed = client.post(f"/jobs/{job['id']}/claim", headers={**access(job), **owner})
    assert claimed.status_code == 200 and claimed.json()["access_type"] == "owned"
    assert submit(client, token).status_code == 410
    assert client.get(f"/jobs/{job['id']}", headers=access(job)).status_code == 404
    retry = client.post(
        f"/jobs/{job['id']}/retry", headers={**owner, "Idempotency-Key": "owner-retry-key"}
    )
    assert retry.status_code == 200 and retry.json()["attempt_count"] == 2
    assert counters(client, token) == (1, 0)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(UsageLedger)) is None
        assert session.get(TranscriptionJob, job["id"]).guest_trial_id is not None


def test_pipeline_success_consumes_once_and_blocks_lifetime_reuse(guest_client, monkeypatch):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    run_service(client, job["id"])
    assert client.get(f"/jobs/{job['id']}", headers=access(job)).json()["status"] == "succeeded"
    assert counters(client, token) == (0, 1)
    assert settle_job_in_factory(client.app.state.session_factory, job["id"], success=True) is False
    assert (
        settle_job_in_factory(client.app.state.session_factory, job["id"], success=False) is False
    )
    assert (
        submit(client, token, key="second-success").json()["detail"]["code"] == "GUEST_TRIAL_USED"
    )
    assert client.delete(f"/jobs/{job['id']}", headers=access(job)).status_code == 204
    assert counters(client, token) == (0, 1)


@pytest.mark.parametrize("terminal", ["delete", "cleanup", "dispatch_timeout"])
def test_unsuccessful_terminal_paths_release_once_and_preserve_history(guest_client, terminal):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    if terminal == "dispatch_timeout":
        client.app.state.job_queue.error = ConnectionError("queue offline")
    job = submit(client, token).json()
    state = client.app.state
    if terminal == "delete":
        assert client.delete(f"/jobs/{job['id']}", headers=access(job)).status_code == 204
    elif terminal == "cleanup":
        result = cleanup_expired_jobs(
            state.session_factory,
            state.storage,
            state.settings,
            now=datetime.now(UTC) + timedelta(days=2),
        )
        assert result.deleted == 1
    else:
        dispatch(client, now=datetime.now(UTC) + timedelta(minutes=16))
        dispatch(client, now=datetime.now(UTC) + timedelta(minutes=17))
    assert counters(client, token) == (0, 0)
    with state.session_factory() as session:
        assert sorted(session.scalars(select(GuestLedger.event_type)).all()) == [
            "release",
            "reservation",
        ]
        assert len(session.scalars(select(GuestDay)).all()) == 1
        assert len(session.scalars(select(GuestSubmission)).all()) == 1
    if terminal != "dispatch_timeout":
        assert submit(client, token).status_code == 410


def test_expired_submission_never_creates_a_replacement(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    with client.app.state.session_factory() as session:
        session.get(TranscriptionJob, job["id"]).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        session.commit()
    assert submit(client, token).status_code == 410
    assert len(client.app.state.job_queue.calls) == 1


def test_ip_day_rolls_at_utc_midnight_and_stores_no_raw_identity(guest_client):
    state = guest_client.app.state
    before = datetime(2026, 10, 8, 7, 59, 50, tzinfo=timezone(timedelta(hours=8)))
    after = before + timedelta(seconds=10)
    with state.session_factory() as session:
        reserve_guest_day(session, state.settings, "private-ip-digest", "first", now=before)
        session.commit()
        with pytest.raises(HTTPException) as error:
            reserve_guest_day(session, state.settings, "private-ip-digest", "blocked", now=before)
        assert error.value.detail == {"code": "GUEST_DAILY_LIMIT", "retry_after": 10}
        session.rollback()
        reserve_guest_day(session, state.settings, "private-ip-digest", "next-day", now=after)
        reserve_guest_day(session, state.settings, "other-ip-digest", "other", now=before)
        session.commit()
        rows = session.scalars(select(GuestDay).order_by(GuestDay.day)).all()
        assert [row.day for row in rows] == ["2026-10-07", "2026-10-07", "2026-10-08"]
        assert len({row.id for row in rows}) == 3
        assert all(len(row.id) == 64 and "private" not in row.id for row in rows)


def test_accepted_submission_replays_after_admission_flags_disabled(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    first = submit(client, token).json()
    client.app.state.settings.guest_usage_enabled = False
    client.app.state.settings.reliable_queue_enabled = False
    replay = submit(client, token)
    assert replay.status_code == 201
    assert replay.json()["id"] == first["id"]
    assert replay.json()["guest_access_token"] == first["guest_access_token"]
    assert counters(client, token) == (1, 0)
    assert len(client.app.state.job_queue.calls) == 1


def test_claimed_guest_retry_cannot_bypass_account_active_limit(guest_client):
    from tests.test_durable_jobs import create

    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    fail(client, job)
    owner = {"Authorization": "Bearer alice"}
    assert (
        client.post(f"/jobs/{job['id']}/claim", headers={**access(job), **owner}).status_code == 200
    )
    assert create(client).status_code == 201
    retry = client.post(
        f"/jobs/{job['id']}/retry", headers={**owner, "Idempotency-Key": "owner-retry-key"}
    )
    assert retry.status_code == 429
    assert retry.json()["detail"]["code"] == "ACTIVE_JOB_EXISTS"
    assert counters(client, token) == (0, 0)


@pytest.mark.parametrize("invalid", ["empty", "corrupt"])
def test_invalid_midi_does_not_consume_guest_trial(guest_client, monkeypatch, invalid):
    import pretty_midi

    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)

    def write_invalid(_scored, path):
        if invalid == "empty":
            pretty_midi.PrettyMIDI().write(str(path))
        else:
            path.write_bytes(b"not a MIDI")

    monkeypatch.setattr("app.services.transcription_artifacts.write_quantized_midi", write_invalid)
    run_service(client, job["id"])
    assert counters(client, token) == (0, 0)
    with client.app.state.session_factory() as session:
        events = session.scalars(select(GuestLedger.event_type)).all()
        assert sorted(events) == ["release", "reservation"]

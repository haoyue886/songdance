"""Offline model stubs verify media transport and settlement, not transcription quality."""

import hashlib
import io
import json
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import numpy as np
import pretty_midi
import pytest
from sqlalchemy import select

from app.models import (
    BillingSubscription,
    JobStatus,
    PaidPeriod,
    TranscriptionJob,
    UsageLedger,
    UsagePeriod,
)
from app.pipeline.errors import NoNotesDetectedError
from app.pipeline.transcribe import NoteEvent
from app.services.paid_periods import grant_paid_period
from app.services.transcription_persistence import mark_failed
from tests.conftest import wav_bytes
from tests.test_creem_billing import billing as billing
from tests.test_creem_billing import event, pay, process
from tests.test_durable_jobs import OWNER, create, dispatch
from tests.test_usage_ledger import protected_client as protected_client
from tests.transcription_helpers import fake_transcription, run_service


@pytest.fixture
def period_clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2030, 1, 31, 23, 59, 59, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            instant = cls.fromtimestamp(cls.current.timestamp(), UTC)
            return instant.replace(tzinfo=None) if tz is None else instant.astimezone(tz)

    for module in (
        "app.routes.jobs",
        "app.services.billing",
        "app.services.billing_events",
        "app.services.dispatch",
        "app.services.durable_jobs",
        "app.services.entitlements",
        "app.services.job_access",
        "app.services.paid_periods",
        "app.services.usage",
    ):
        monkeypatch.setattr(f"{module}.datetime", Clock)
    return Clock


@pytest.fixture
def durable(protected_client):
    protected_client.app.state.settings.reliable_queue_enabled = True
    protected_client.app.state.settings.usage_enabled = True
    return protected_client


def grant_pro_period(client, clock, *, renewal=False):
    client.app.state.settings.paid_usage_enabled = True
    user = client.get("/me", headers=OWNER)
    assert user.status_code == 200
    with client.app.state.session_factory.begin() as session:
        return grant_paid_period(
            session,
            user_id=user.json()["id"],
            environment="test",
            transaction_id="tx-renewal" if renewal else "tx-first",
            subscription_id="sub-cross-period",
            product_id="test-product",
            plan_version="test-v1",
            amount_minor=990,
            currency="USD",
            period_start=clock(2030, 2 if renewal else 1, 1, tzinfo=UTC),
            period_end=clock(2030, 3 if renewal else 2, 1, tzinfo=UTC),
            limit_seconds=1800,
            max_clip_seconds=90,
        )


def reservation(client, job_id):
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        row = session.scalar(
            select(UsageLedger).where(
                UsageLedger.reservation_id == job.usage_reservation_id,
                UsageLedger.event_type == "reservation",
            )
        )
        return row.reservation_id, row.period_id, row.units


def assert_period(client, period_id, reserved, consumed):
    with client.app.state.session_factory() as session:
        period = session.get(UsagePeriod, period_id)
        assert (period.reserved_units, period.consumed_units) == (reserved, consumed)


def assert_events(client, reservation_id, period_id, units, *expected):
    with client.app.state.session_factory() as session:
        rows = session.scalars(
            select(UsageLedger).where(UsageLedger.reservation_id == reservation_id)
        ).all()
        assert sorted(row.event_type for row in rows) == sorted(expected)
        assert all(row.period_id == period_id and row.units == units for row in rows)


def finish(client, job_id, monkeypatch, success):
    def no_notes(*_args, **_kwargs):
        raise NoNotesDetectedError()

    monkeypatch.setattr(
        "app.services.transcription.transcribe_audio", fake_transcription if success else no_notes
    )
    run_service(client, job_id)
    response = client.get(f"/jobs/{job_id}", headers=OWNER)
    assert response.status_code == 200
    assert response.json()["status"] == ("succeeded" if success else "failed")
    if success:
        link = client.get(f"/jobs/{job_id}/download-url/midi", headers=OWNER)
        assert link.status_code == 200
        download = client.get(link.json()["path"])
        assert download.status_code == 200 and download.content.startswith(b"MThd")
    else:
        assert response.json()["error_code"] == "NO_NOTES_DETECTED"


@pytest.mark.parametrize("success", [True, False], ids=["consume", "release"])
def test_free_cross_utc_month_settles_old_month_without_adding_new_allowance(
    durable, period_clock, monkeypatch, success
):
    client = durable
    created = create(client)
    assert created.status_code == 201
    old_id = created.json()["id"]
    old_reservation, old_period, units = reservation(client, old_id)
    with client.app.state.session_factory() as session:
        assert session.get(UsagePeriod, old_period).period_key == "free:2030-01"

    period_clock.current = period_clock(2030, 2, 1, tzinfo=UTC)
    summary = client.get("/billing/me", headers=OWNER).json()
    assert (summary["plan"], summary["remaining"], summary["used"]) == ("free", 1, 0)
    finish(client, old_id, monkeypatch, success)
    assert_period(client, old_period, 0, int(success))
    assert_events(
        client,
        old_reservation,
        old_period,
        units,
        "reservation",
        "consume" if success else "release",
    )

    new = create(client, key="new-month-key")
    assert new.status_code == 201
    new_id = new.json()["id"]
    new_reservation, new_period, new_units = reservation(client, new_id)
    assert new_period != old_period
    with client.app.state.session_factory() as session:
        period = session.get(UsagePeriod, new_period)
        assert (period.period_key, period.limit_units) == ("free:2030-02", 1)
    mark_failed(
        client.app.state.session_factory, old_id, "LATE_FAILURE", "late", expected_attempt=1
    )
    run_service(client, old_id)
    assert_period(client, new_period, 1, 0)
    assert_events(client, new_reservation, new_period, new_units, "reservation")

    finish(client, new_id, monkeypatch, True)
    assert_period(client, new_period, 0, 1)
    blocked = create(client, key="new-month-exhausted")
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "FREE_MONTHLY_LIMIT"
    assert_period(client, old_period, 0, int(success))


@pytest.mark.parametrize("success", [True, False], ids=["consume", "release"])
@pytest.mark.parametrize("renewal", [True, False], ids=["new-pro-period", "return-to-free"])
def test_accepted_pro_job_outlives_paid_period_without_charging_current_entitlement(
    durable, period_clock, monkeypatch, renewal, success
):
    client = durable
    old = grant_pro_period(client, period_clock)
    new = grant_pro_period(client, period_clock, renewal=True) if renewal else None
    created = create(client)
    assert created.status_code == 201
    job_id = created.json()["id"]
    expires_at = created.json()["expires_at"]
    old_reservation, old_period, units = reservation(client, job_id)
    assert old_period == old.usage_period_id and units == 15
    assert_period(client, old_period, 15, 0)

    period_clock.current = period_clock(2030, 2, 1, tzinfo=UTC)
    before = client.get("/billing/me", headers=OWNER).json()
    assert (before["plan"], before["remaining"]) == (("pro", 1800) if renewal else ("free", 1))
    finish(client, job_id, monkeypatch, success)
    assert client.get(f"/jobs/{job_id}", headers=OWNER).json()["expires_at"] == expires_at
    assert_period(client, old_period, 0, 15 if success else 0)
    assert_events(
        client,
        old_reservation,
        old_period,
        units,
        "reservation",
        "consume" if success else "release",
    )
    after = client.get("/billing/me", headers=OWNER).json()
    assert (after["plan"], after["reserved"], after["used"], after["remaining"]) == (
        before["plan"],
        0,
        0,
        before["remaining"],
    )
    assert after["task_summary"] == {"succeeded": 0, "failed": 0, "in_progress": 0}
    if new is not None:
        assert_period(client, new.usage_period_id, 0, 0)
    current_job = create(client, key="current-entitlement")
    assert current_job.status_code == 201
    _, current_period, current_units = reservation(client, current_job.json()["id"])
    assert current_period != old_period and current_units == (15 if renewal else 1)
    assert_period(client, current_period, current_units, 0)
    mark_failed(
        client.app.state.session_factory, job_id, "LATE_FAILURE", "late", expected_attempt=1
    )
    run_service(client, job_id)
    assert_period(client, current_period, current_units, 0)
    assert_period(client, old_period, 0, 15 if success else 0)


@pytest.mark.parametrize("success", [True, False], ids=["consume", "release"])
def test_canceled_subscription_keeps_accepted_job_valid_after_period_end(
    billing, period_clock, monkeypatch, success
):
    client, provider = billing
    client.app.state.settings.reliable_queue_enabled = True
    start, end = period_clock(2030, 1, 1, tzinfo=UTC), period_clock(2030, 2, 1, tzinfo=UTC)
    provider.subscription.update(
        updated_at=start.isoformat(),
        current_period_start_date=start.isoformat(),
        current_period_end_date=end.isoformat(),
    )
    provider.transactions["tx_test"].update(
        period_start=int(start.timestamp() * 1000), period_end=int(end.timestamp() * 1000)
    )
    pay(client, provider)
    created = create(client)
    assert created.status_code == 201
    job_id = created.json()["id"]
    old_reservation, old_period, units = reservation(client, job_id)

    provider.subscription.update(
        status="scheduled_cancel", updated_at=period_clock.now(UTC).isoformat()
    )
    assert event(client, "subscription.scheduled_cancel", "evt_scheduled").status_code == 200
    assert process(client, provider) == 1
    period_clock.current = end
    provider.subscription.update(status="canceled", updated_at=end.isoformat())
    assert event(client, "subscription.canceled", "evt_canceled").status_code == 200
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingSubscription)).status == "canceled"
        assert session.scalar(select(PaidPeriod)).status == "active"
    assert client.get("/billing/me", headers=OWNER).json()["plan"] == "free"

    finish(client, job_id, monkeypatch, success)
    assert_period(client, old_period, 0, 15 if success else 0)
    assert_events(
        client,
        old_reservation,
        old_period,
        units,
        "reservation",
        "consume" if success else "release",
    )
    new = create(client, key="after-cancel-free")
    assert new.status_code == 201
    _, free_period, free_units = reservation(client, new.json()["id"])
    assert free_units == 1 and free_period != old_period
    assert_period(client, free_period, 1, 0)


def assert_late_attempt_cannot_settle_new_period(client, period_clock, monkeypatch, plan):
    if plan == "pro":
        grant_pro_period(client, period_clock)
        grant_pro_period(client, period_clock, renewal=True)
    created = create(client)
    assert created.status_code == 201
    job_id = created.json()["id"]
    old_reservation, old_period, units = reservation(client, job_id)
    entered, release = Event(), Event()
    calls = []

    def held_transcription(path, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(30), "old model call was not released"
        return fake_transcription(path, **kwargs)

    monkeypatch.setattr("app.services.transcription.transcribe_audio", held_transcription)
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(run_service, client, job_id)
        try:
            assert entered.wait(30), "old worker never reached the model"
            period_clock.current = period_clock(2030, 2, 1, 0, 16, tzinfo=UTC)
            assert dispatch(client) == 1
            response = client.get(f"/jobs/{job_id}", headers=OWNER)
            assert response.json()["status"] == "failed"
            assert response.json()["error_code"] == "WORKER_LOST"
            assert_period(client, old_period, 0, 0)
            retry = client.post(
                f"/jobs/{job_id}/retry", headers={**OWNER, "Idempotency-Key": "cross-period-retry"}
            )
            assert retry.status_code == 200, retry.text
            assert retry.json()["attempt_count"] == 2
            new_reservation, new_period, new_units = reservation(client, job_id)
            assert new_period != old_period and new_reservation != old_reservation
        finally:
            release.set()
        running.result(timeout=30)

    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert (job.status, job.attempt_count, job.usage_reservation_id) == (
            JobStatus.QUEUED,
            2,
            new_reservation,
        )
        assert job.result is None and job.artifacts == []
    assert_period(client, old_period, 0, 0)
    assert_period(client, new_period, new_units, 0)
    assert_events(client, old_reservation, old_period, units, "reservation", "release")
    assert_events(client, new_reservation, new_period, new_units, "reservation")
    assert client.app.state.job_queue.calls == [(job_id, 1), (job_id, 2)]

    run_service(client, job_id)
    assert calls == [1, 1]
    assert_period(client, old_period, 0, 0)
    assert_period(client, new_period, 0, new_units)
    assert_events(client, new_reservation, new_period, new_units, "reservation", "consume")
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job.status == JobStatus.SUCCEEDED
        assert all("/attempt-2/" in item.storage_key for item in job.artifacts)


@pytest.mark.parametrize("plan", ["free", "pro"])
def test_late_worker_after_cross_period_retry_never_settles_new_reservation(
    durable, period_clock, monkeypatch, plan
):
    assert_late_attempt_cannot_settle_new_period(durable, period_clock, monkeypatch, plan)


def segmented_wav(duration):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        for length, frequency in ((5, 220), (1, 440), (duration - 2, 660), (1, 880), (5, 1100)):
            with wave.open(io.BytesIO(wav_bytes(length, frequency=frequency)), "rb") as part:
                output.writeframes(part.readframes(part.getnframes()))
    return buffer.getvalue()


def wav_details(path):
    with wave.open(str(path), "rb") as audio:
        rate = audio.getframerate()
        assert audio.getnchannels() == 1 and audio.getsampwidth() == 2
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
    return rate, samples


def frequency_at(samples, rate, start):
    window = samples[round(start * rate) : round((start + 0.25) * rate)]
    spectrum = np.abs(np.fft.rfft(window * np.hanning(len(window))))
    return np.fft.rfftfreq(len(window), 1 / rate)[np.argmax(spectrum)]


@pytest.mark.parametrize(
    "duration,units", [(30.1, 31), (90, 90)], ids=["ceil-seconds", "current-cap"]
)
def test_complete_selected_clip_is_metered_stored_and_sent_to_model(
    durable, period_clock, monkeypatch, tmp_path: Path, duration, units
):
    client = durable
    paid = grant_pro_period(client, period_clock)
    upload = segmented_wav(duration)
    created = create(
        client,
        content=upload,
        start_sec="5",
        end_sec=str(5 + duration),
        duration_seconds="1",
        charge_seconds="1",
    )
    assert created.status_code == 201
    job_id = created.json()["id"]
    reservation_id, period_id, charged = reservation(client, job_id)
    assert period_id == paid.usage_period_id and charged == units
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        asset = job.source_asset
        assert (job.start_sec, job.end_sec) == (5, 5 + duration)
        assert asset.duration_sec == pytest.approx(duration, abs=1 / 44100)
        source = tmp_path / "stored-source.wav"
        client.app.state.storage.download_file(asset.storage_key, source)
        assert asset.size_bytes == source.stat().st_size
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        assert asset.sha256 == digest and digest != hashlib.sha256(upload).hexdigest()
        row = session.scalar(
            select(UsageLedger).where(UsageLedger.reservation_id == reservation_id)
        )
        assert json.loads(row.details)["duration_seconds"] == pytest.approx(duration, abs=1 / 44100)
    rate, samples = wav_details(source)
    assert rate == 44100 and len(samples) / rate == pytest.approx(duration, abs=1 / rate)
    assert frequency_at(samples, rate, 0.25) == pytest.approx(440, abs=8)
    assert frequency_at(samples, rate, duration / 2) == pytest.approx(660, abs=8)
    assert frequency_at(samples, rate, duration - 0.75) == pytest.approx(880, abs=8)
    observed = []

    def inspect_model_input(path, **kwargs):
        model_rate, model_samples = wav_details(path)
        assert model_rate == 22050
        assert len(model_samples) / model_rate == pytest.approx(duration, abs=2 / model_rate)
        assert frequency_at(model_samples, model_rate, 0.25) == pytest.approx(440, abs=8)
        assert frequency_at(model_samples, model_rate, duration / 2) == pytest.approx(660, abs=8)
        assert frequency_at(model_samples, model_rate, duration - 0.75) == pytest.approx(880, abs=8)
        observed.append(len(model_samples))
        events, midi = fake_transcription(path, **kwargs)
        events.append(NoteEvent(duration - 1, duration, 72, 100, 0.9))
        midi.instruments[0].notes.append(
            pretty_midi.Note(velocity=100, pitch=72, start=duration - 1, end=duration)
        )
        return events, midi

    monkeypatch.setattr("app.services.transcription.transcribe_audio", inspect_model_input)
    run_service(client, job_id)
    assert len(observed) == 1
    assert_period(client, period_id, 0, units)
    assert_events(client, reservation_id, period_id, units, "reservation", "consume")
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job.status == JobStatus.SUCCEEDED
        timeline = next(item for item in job.artifacts if item.type == "raw_timeline")
        path = tmp_path / "raw-timeline.json"
        client.app.state.storage.download_file(timeline.storage_key, path)
        raw = json.loads(path.read_text())
        assert any(note["end_sec"] == duration for note in raw["notes"])


def test_selected_clip_over_current_cap_is_rejected_before_reservation(durable, period_clock):
    paid = grant_pro_period(durable, period_clock)
    response = create(
        durable, content=wav_bytes(96), start_sec="5", end_sec="95.001", duration_seconds="1"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_CLIP"
    assert_period(durable, paid.usage_period_id, 0, 0)
    with durable.app.state.session_factory() as session:
        assert session.scalars(select(UsageLedger)).all() == []
        assert session.scalars(select(TranscriptionJob)).all() == []
    assert durable.app.state.job_queue.calls == []

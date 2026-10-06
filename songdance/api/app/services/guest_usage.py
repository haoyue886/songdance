"""Signed visitor identity, IP-day admissions and append-only trial settlement."""

import hashlib
import hmac
import json
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import GuestDay, GuestLedger, GuestSubmission, GuestTrial, TranscriptionJob
from app.services.job_access import get_available_job
from app.settings import Settings


def _mac(settings: Settings, value: str) -> str:
    return hmac.new(
        settings.guest_signing_secret.get_secret_value().encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def issue_visitor(settings: Settings) -> str:
    nonce = secrets.token_hex(32)
    return f"v1.{nonce}.{_mac(settings, 'visitor:v1:' + nonce)}"


def visitor_id(settings: Settings, token: str | None) -> str:
    if not isinstance(token, str) or not re.fullmatch(r"v1\.[a-f0-9]{64}\.[a-f0-9]{64}", token):
        raise HTTPException(401, detail={"code": "VISITOR_REQUIRED"})
    _, nonce, signature = token.split(".")
    if not hmac.compare_digest(signature, _mac(settings, "visitor:v1:" + nonce)):
        raise HTTPException(401, detail={"code": "VISITOR_INVALID"})
    return _mac(settings, "trial:" + nonce)


def visitor_job_secret(settings: Settings, trial_id: str, job_id: str) -> tuple[str, str]:
    token = _mac(settings, f"job-capability:{trial_id}:{job_id}")
    return token, hashlib.sha256(token.encode()).hexdigest()


def _write_transaction(session: Session) -> None:
    if session.get_bind().dialect.name == "sqlite":
        connection = session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")


def lock_trial(session: Session, trial_id: str) -> GuestTrial:
    _write_transaction(session)
    trial = session.get(GuestTrial, trial_id)
    if trial is None:
        try:
            with session.begin_nested():
                session.add(GuestTrial(id=trial_id, reserved=0, consumed=0))
                session.flush()
        except IntegrityError:
            pass
    # An UPDATE serializes SQLite too; the lock is not a balance mutation.
    session.execute(
        update(GuestTrial)
        .where(GuestTrial.id == trial_id)
        .values(reserved=GuestTrial.reserved)
        .execution_options(synchronize_session=False)
    )
    return session.scalars(
        select(GuestTrial)
        .where(GuestTrial.id == trial_id)
        .execution_options(populate_existing=True)
    ).one()


def reserve_trial(session: Session, trial_id: str, job_id: str) -> str:
    trial = lock_trial(session, trial_id)
    if trial.consumed:
        raise HTTPException(429, detail={"code": "GUEST_TRIAL_USED"})
    if trial.reserved:
        raise HTTPException(429, detail={"code": "GUEST_TRIAL_ACTIVE"})
    trial.reserved = 1
    reservation = secrets.token_urlsafe(24)
    session.add(
        GuestLedger(
            id=secrets.token_urlsafe(24),
            trial_id=trial_id,
            job_id=job_id,
            reservation_id=reservation,
            event_type="reservation",
        )
    )
    return reservation


def reserve_guest_day(
    session: Session,
    settings: Settings,
    ip_digest: str,
    job_id: str,
    *,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    day = current.astimezone(UTC).date().isoformat()
    identity = _mac(settings, f"ip-day:{day}:{ip_digest}")
    try:
        with session.begin_nested():
            session.add(GuestDay(id=identity, day=day, job_id=job_id))
            session.flush()
    except IntegrityError:
        end = datetime.combine(
            current.astimezone(UTC).date() + timedelta(days=1), datetime.min.time(), UTC
        )
        seconds = max(1, int((end - current).total_seconds()))
        raise HTTPException(
            429,
            headers={"Retry-After": str(seconds)},
            detail={"code": "GUEST_DAILY_LIMIT", "retry_after": seconds},
        ) from None


def settle_guest(session: Session, job: TranscriptionJob, success: bool, reason: str) -> bool:
    if not job.guest_reservation_id:
        return False
    reservation = session.scalar(
        select(GuestLedger).where(
            GuestLedger.reservation_id == job.guest_reservation_id,
            GuestLedger.event_type == "reservation",
        )
    )
    if reservation is None:
        raise RuntimeError("Guest reservation is missing")
    trial = lock_trial(session, reservation.trial_id)
    if session.scalar(
        select(GuestLedger.id).where(
            GuestLedger.reservation_id == reservation.reservation_id,
            GuestLedger.event_type.in_(["consume", "release"]),
        )
    ):
        return False
    if trial.reserved != 1:
        raise RuntimeError("Guest reservation counters disagree")
    trial.reserved = 0
    if success:
        trial.consumed = 1
    session.add(
        GuestLedger(
            id=secrets.token_urlsafe(24),
            trial_id=trial.id,
            job_id=job.id,
            reservation_id=reservation.reservation_id,
            event_type="consume" if success else "release",
            reason=json.dumps({"source": reason}, separators=(",", ":")),
        )
    )
    return True


def replay_guest(
    session: Session,
    trial_id: str,
    key: str,
    fingerprint: str,
    operation: str,
) -> TranscriptionJob | None:
    lock_trial(session, trial_id)
    row = session.scalar(
        select(GuestSubmission).where(
            GuestSubmission.trial_id == trial_id,
            GuestSubmission.submission_key == key,
        )
    )
    if row is None:
        return None
    if row.fingerprint != fingerprint or row.operation != operation:
        raise HTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})
    job = session.get(TranscriptionJob, row.job_id)
    if job is None or job.owner_user_id is not None or job.guest_trial_id != trial_id:
        raise HTTPException(410, detail={"code": "SUBMISSION_EXPIRED"})
    try:
        return get_available_job(session, job.id)
    except HTTPException as error:
        if error.status_code == 404:
            raise HTTPException(410, detail={"code": "SUBMISSION_EXPIRED"}) from error
        raise


def record_guest_submission(
    session: Session, trial_id: str, key: str, fingerprint: str, job_id: str, operation: str
) -> None:
    session.add(
        GuestSubmission(
            id=secrets.token_urlsafe(24),
            trial_id=trial_id,
            submission_key=key,
            fingerprint=fingerprint,
            job_id=job_id,
            operation=operation,
        )
    )

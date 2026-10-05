import json
import secrets
from datetime import UTC, datetime, time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import TranscriptionJob, UsageLedger, UsagePeriod, User
from app.settings import Settings


class UsageExceeded(Exception):
    retry_after: int

    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__("Free monthly usage is exhausted")


def utc_month(now: datetime | None = None) -> tuple[str, datetime, datetime]:
    current = _as_utc(now or datetime.now(UTC))
    start = datetime.combine(current.date().replace(day=1), time.min, UTC)
    if current.month == 12:
        end = datetime.combine(
            current.date().replace(year=current.year + 1, month=1, day=1), time.min, UTC
        )
    else:
        end = datetime.combine(
            current.date().replace(month=current.month + 1, day=1), time.min, UTC
        )
    return f"free:{start:%Y-%m}", start, end


def _period(
    session: Session, user_id: str, settings: Settings, now: datetime | None = None
) -> UsagePeriod:
    key, start, end = utc_month(now)
    statement = (
        select(UsagePeriod)
        .where(
            UsagePeriod.user_id == user_id,
            UsagePeriod.entitlement_type == "free_month",
            UsagePeriod.period_key == key,
        )
        .with_for_update()
    )
    current = session.scalar(statement)
    if current is not None:
        return current
    current = UsagePeriod(
        id=secrets.token_urlsafe(24),
        user_id=user_id,
        entitlement_type="free_month",
        period_key=key,
        period_start=start,
        period_end=end,
        limit_units=settings.free_monthly_job_limit,
    )
    try:
        with session.begin_nested():
            session.add(current)
            session.flush()
    except IntegrityError:
        current = session.scalar(statement)
        if current is None:
            raise
    return current


def reserve_free(session: Session, user: User, job_id: str, settings: Settings) -> str:
    current = _period(session, user.id, settings)
    if current.consumed_units + current.reserved_units >= current.limit_units:
        period_end = _as_utc(current.period_end)
        raise UsageExceeded(max(1, int((period_end - datetime.now(UTC)).total_seconds())))
    reservation_id = secrets.token_urlsafe(24)
    current.reserved_units += 1
    session.add(
        UsageLedger(
            id=secrets.token_urlsafe(24),
            period_id=current.id,
            user_id=user.id,
            job_id=job_id,
            reservation_id=reservation_id,
            event_type="reservation",
            units=1,
            details="{}",
        )
    )
    return reservation_id


def _settle(session: Session, reservation_id: str, success: bool, reason: str) -> bool:
    reservation = session.scalar(
        select(UsageLedger).where(
            UsageLedger.reservation_id == reservation_id, UsageLedger.event_type == "reservation"
        )
    )
    if reservation is None:
        return False
    terminal_type = "consume" if success else "release"
    existing = session.scalar(
        select(UsageLedger).where(
            UsageLedger.reservation_id == reservation_id, UsageLedger.event_type == terminal_type
        )
    )
    if existing is not None:
        return False
    period = session.scalar(
        select(UsagePeriod).where(UsagePeriod.id == reservation.period_id).with_for_update()
    )
    if period is None or period.reserved_units < reservation.units:
        return False
    period.reserved_units -= reservation.units
    if success:
        period.consumed_units += reservation.units
    session.add(
        UsageLedger(
            id=secrets.token_urlsafe(24),
            period_id=reservation.period_id,
            user_id=reservation.user_id,
            job_id=reservation.job_id,
            reservation_id=reservation_id,
            event_type=terminal_type,
            units=reservation.units,
            details=json.dumps({"source": reason}, separators=(",", ":")),
        )
    )
    return True


def settle_job(
    session: Session, job: TranscriptionJob, *, success: bool, reason: str = "worker"
) -> bool:
    if not job.usage_reservation_id:
        return False
    changed = _settle(session, job.usage_reservation_id, success, reason)
    if changed:
        session.commit()
    return changed


def settle_job_in_factory(
    factory: sessionmaker[Session],
    job_id: str,
    *,
    success: bool,
    expected_attempt: int | None = None,
    reservation_id: str | None = None,
    reason: str = "worker",
) -> bool:
    with factory() as session:
        job = session.scalar(
            select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()
        )
        if job is None:
            return False
        if expected_attempt is not None and job.attempt_count != expected_attempt:
            return False
        if reservation_id is not None and job.usage_reservation_id != reservation_id:
            return False
        return settle_job(session, job, success=success, reason=reason)


def release_job_reservation(
    session: Session, job: TranscriptionJob, *, reason: str = "worker"
) -> bool:
    return settle_job(session, job, success=False, reason=reason)


def usage_http_error(error: UsageExceeded) -> HTTPException:
    return HTTPException(
        status_code=429,
        headers={"Retry-After": str(error.retry_after)},
        detail={
            "code": "FREE_MONTHLY_LIMIT",
            "message": "本月免费转录次数已用完",
            "retry_after": error.retry_after,
        },
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

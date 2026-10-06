import json
import secrets
from datetime import UTC, datetime, time

from fastapi import HTTPException
from sqlalchemy import select, update
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
    return reserve_period(session, _period(session, user.id, settings), job_id, 1)


def reserve_period(
    session: Session,
    current: UsagePeriod,
    job_id: str,
    units: int,
    *,
    details: dict[str, object] | None = None,
) -> str:
    """Reserve atomically, including on SQLite; the caller owns commit/rollback."""
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise ValueError("Reservation units must be positive integers")
    result = session.execute(
        update(UsagePeriod)
        .where(
            UsagePeriod.id == current.id,
            UsagePeriod.reserved_units + UsagePeriod.consumed_units + units
            <= UsagePeriod.limit_units,
        )
        .values(reserved_units=UsagePeriod.reserved_units + units)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        period_end = _as_utc(current.period_end)
        raise UsageExceeded(max(1, int((period_end - datetime.now(UTC)).total_seconds())))
    reservation_id = secrets.token_urlsafe(24)
    session.expire(current, ["reserved_units", "consumed_units"])
    session.add(
        UsageLedger(
            id=secrets.token_urlsafe(24),
            period_id=current.id,
            user_id=current.user_id,
            job_id=job_id,
            reservation_id=reservation_id,
            event_type="reservation",
            units=units,
            details=json.dumps(details or {}, separators=(",", ":")),
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
    # Serialize both terminal types on the same period before checking either one.
    session.execute(
        update(UsagePeriod)
        .where(UsagePeriod.id == reservation.period_id)
        .values(reserved_units=UsagePeriod.reserved_units)
        .execution_options(synchronize_session=False)
    )
    terminal_type = "consume" if success else "release"
    existing = session.scalar(
        select(UsageLedger).where(
            UsageLedger.reservation_id == reservation_id,
            UsageLedger.event_type.in_(["consume", "release"]),
        )
    )
    if existing is not None:
        return False
    result = session.execute(
        update(UsagePeriod)
        .where(
            UsagePeriod.id == reservation.period_id, UsagePeriod.reserved_units >= reservation.units
        )
        .values(
            reserved_units=UsagePeriod.reserved_units - reservation.units,
            consumed_units=UsagePeriod.consumed_units + (reservation.units if success else 0),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise RuntimeError("Usage reservation counters are inconsistent")
    period = session.get(UsagePeriod, reservation.period_id)
    if period is not None:
        session.expire(period, ["reserved_units", "consumed_units"])
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
    if job.guest_reservation_id:
        from app.services.guest_usage import settle_guest

        return settle_guest(session, job, success, reason)
    if not job.usage_reservation_id:
        return False
    return _settle(session, job.usage_reservation_id, success, reason)


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
        if expected_attempt is not None:
            if job.usage_reservation_id != reservation_id:
                return False
            if success and (
                job.status != "succeeded" or job.error_code in {"DELETE_REQUESTED", "DELETE_FAILED"}
            ):
                return False
            if not success and job.status != "failed":
                return False
        if reservation_id is not None and job.usage_reservation_id != reservation_id:
            return False
        changed = settle_job(session, job, success=success, reason=reason)
        session.commit()
        return changed


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

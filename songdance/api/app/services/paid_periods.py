"""Local projection of already verified payment facts; never verifies a provider payment.

Callers must bind identity, environment, product and payment with authoritative provider
facts before calling this module. There is deliberately no HTTP grant endpoint. All
writes participate in the caller's transaction; none of these functions commits it.
"""

import hashlib
import re
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.paid_period import PaidPeriod
from app.models.usage import UsagePeriod
from app.models.user import User


class PaidPeriodConflict(ValueError):
    """Payment facts conflict with an existing immutable grant."""


def _text(value: str, name: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be nonempty and at most {maximum} characters")
    if value != value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError(f"{name} must not contain surrounding whitespace or controls")
    return value


def _environment(value: str) -> str:
    if value not in ("test", "live"):
        raise ValueError("environment must be test or live")
    return value


def _positive(value: int, name: str, maximum: int = 2_147_483_647) -> int:
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("payment timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _stored_utc(value: datetime) -> datetime:
    # SQLite strips timezone metadata from DateTime(timezone=True) values.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _lock_user(session: Session, user_id: str) -> None:
    _text(user_id, "user_id", 36)
    if session.get_bind().dialect.name == "sqlite":
        # SQLite ignores FOR UPDATE. Acquire its writer lock before reading grants.
        session.execute(update(User).where(User.id == user_id).values(active=User.active))
    user = session.scalar(select(User).where(User.id == user_id).with_for_update(key_share=True))
    if user is None or not user.active:
        raise ValueError("payment user must exist and be active")


def grant_paid_period(
    session: Session,
    *,
    user_id: str,
    environment: str,
    transaction_id: str,
    subscription_id: str,
    product_id: str,
    plan_version: str,
    amount_minor: int,
    currency: str,
    period_start: datetime,
    period_end: datetime,
    limit_seconds: int = 1800,
    max_clip_seconds: int = 90,
) -> PaidPeriod:
    """Grant verified facts once; reject conflicting replay instead of changing usage."""
    environment = _environment(environment)
    for name, value in (
        ("transaction_id", transaction_id),
        ("subscription_id", subscription_id),
        ("product_id", product_id),
    ):
        _text(value, name)
    _text(plan_version, "plan_version", 64)
    _positive(amount_minor, "amount_minor")
    _positive(limit_seconds, "limit_seconds")
    _positive(max_clip_seconds, "max_clip_seconds", 90)
    if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise ValueError("currency must be a three-letter uppercase code")
    start, end = _utc(period_start), _utc(period_end)
    if end <= start:
        raise ValueError("period_end must be after period_start")
    _lock_user(session, user_id)
    if session.get_bind().dialect.name == "postgresql":
        # Two different users have different row locks. Serialize the first binding
        # of a provider subscription as well, including non-overlapping renewals.
        binding = f"paid-subscription:{environment}:{subscription_id}".encode()
        key = int.from_bytes(hashlib.sha256(binding).digest()[:8], "big", signed=True)
        session.execute(select(func.pg_advisory_xact_lock(key)))
    existing = session.scalar(
        select(PaidPeriod)
        .where(PaidPeriod.environment == environment, PaidPeriod.transaction_id == transaction_id)
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        usage = session.get(UsagePeriod, existing.usage_period_id)
        same = all(
            (
                existing.user_id == user_id,
                existing.subscription_id == subscription_id,
                existing.product_id == product_id,
                existing.plan_version == plan_version,
                existing.amount_minor == amount_minor,
                existing.currency == currency,
                _stored_utc(existing.period_start) == start,
                _stored_utc(existing.period_end) == end,
                existing.max_clip_seconds == max_clip_seconds,
                usage is not None
                and usage.user_id == user_id
                and usage.entitlement_type == "pro_paid"
                and usage.limit_units == limit_seconds,
            )
        )
        if not same:
            raise PaidPeriodConflict("transaction conflicts with its existing grant")
        return existing
    subscription_owner = session.scalar(
        select(PaidPeriod.user_id)
        .where(
            PaidPeriod.environment == environment,
            PaidPeriod.subscription_id == subscription_id,
            PaidPeriod.user_id != user_id,
        )
        .limit(1)
    )
    if subscription_owner is not None:
        raise PaidPeriodConflict("subscription belongs to another user")
    overlap = session.scalar(
        select(PaidPeriod.id)
        .where(
            PaidPeriod.user_id == user_id,
            PaidPeriod.environment == environment,
            PaidPeriod.period_start < end,
            PaidPeriod.period_end > start,
        )
        .limit(1)
    )
    # Keep revoked/frozen periods unique too: their interval must not silently gain
    # replacement entitlement or fall back to Free while awaiting reconciliation.
    if overlap is not None:
        raise PaidPeriodConflict("paid period overlaps an existing grant")
    paid_id = secrets.token_urlsafe(24)
    usage = UsagePeriod(
        id=secrets.token_urlsafe(24),
        user_id=user_id,
        entitlement_type="pro_paid",
        period_key=f"paid:{environment}:{paid_id}",
        period_start=start,
        period_end=end,
        limit_units=limit_seconds,
        reserved_units=0,
        consumed_units=0,
    )
    paid = PaidPeriod(
        id=paid_id,
        user_id=user_id,
        environment=environment,
        transaction_id=transaction_id,
        subscription_id=subscription_id,
        product_id=product_id,
        plan_version=plan_version,
        amount_minor=amount_minor,
        currency=currency,
        period_start=start,
        period_end=end,
        max_clip_seconds=max_clip_seconds,
        status="active",
        usage_period_id=usage.id,
    )
    try:
        with session.begin_nested():
            session.add(usage)
            session.flush()
            session.add(paid)
            session.flush()
    except IntegrityError as error:
        raise PaidPeriodConflict("payment grant violates an existing binding") from error
    return paid


def current_paid_period(
    session: Session,
    *,
    user_id: str,
    environment: str,
    now: datetime | None = None,
) -> PaidPeriod | None:
    """Return the covering period, INCLUDING frozen/revoked ones.

    Callers must deny new usage for non-active periods rather than fall back to Free.
    None means no paid coverage in this environment (including normal expiry).
    """
    _text(user_id, "user_id", 36)
    environment = _environment(environment)
    current = _utc(now) if now is not None else datetime.now(UTC)
    return session.scalars(
        select(PaidPeriod)
        .where(
            PaidPeriod.user_id == user_id,
            PaidPeriod.environment == environment,
            PaidPeriod.period_start <= current,
            PaidPeriod.period_end > current,
        )
        .execution_options(populate_existing=True)
    ).one_or_none()


def set_paid_period_status(
    session: Session,
    *,
    user_id: str,
    environment: str,
    transaction_id: str,
    status: str,
) -> PaidPeriod:
    """Apply a verified refund/freeze to one transaction, never to a later renewal.

    Reinstatement requires separate provider reconciliation and is not exposed here.
    A stale freeze cannot downgrade an already final revoked status.
    """
    environment = _environment(environment)
    _text(transaction_id, "transaction_id")
    if status not in ("revoked", "frozen"):
        raise ValueError("status must be revoked or frozen")
    _lock_user(session, user_id)
    paid = session.scalar(
        select(PaidPeriod)
        .where(
            PaidPeriod.user_id == user_id,
            PaidPeriod.environment == environment,
            PaidPeriod.transaction_id == transaction_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if paid is None:
        raise PaidPeriodConflict("transaction does not belong to this user and environment")
    if paid.status != "revoked":
        paid.status = status
    session.flush()
    return paid

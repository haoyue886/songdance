"""Admission against local entitlements. Payment verification belongs to the provider adapter."""

import math
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import JobStatus, TranscriptionJob, UsagePeriod, User
from app.services.paid_periods import current_paid_period
from app.services.usage import UsageExceeded, _as_utc, reserve_free, reserve_period, utc_month
from app.settings import Settings


def charge_seconds(duration: float) -> int:
    if isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Decoded duration must be finite and positive")
    return max(15, math.ceil(duration))


def lock_usage_user(session: Session, user_id: str) -> None:
    if session.get_bind().dialect.name == "sqlite":
        session.execute(update(User).where(User.id == user_id).values(active=User.active))
    # Serialize admissions without blocking FK KEY SHARE checks from settlement.
    session.scalar(select(User).where(User.id == user_id).with_for_update(key_share=True))


def _error(code: str, message: str, status: int = 429) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def reserve_job(
    session: Session,
    user: User,
    job_id: str,
    settings: Settings,
    *,
    duration: float,
    attempt: int = 1,
) -> str:
    """Duration comes from the server-decoded source asset, never browser billing fields."""
    seconds = charge_seconds(duration)
    lock_usage_user(session, user.id)
    paid = (
        current_paid_period(session, user_id=user.id, environment=settings.billing_environment)
        if settings.paid_usage_enabled
        else None
    )
    if paid is None:
        if duration > 90:
            raise _error("INVALID_CLIP", "免费转录最长 90 秒", 422)
        reservation = reserve_free(session, user, job_id, settings)
    else:
        if paid.status != "active":
            raise _error("ENTITLEMENT_SUSPENDED", "当前付费权益已暂停，请联系支持", 403)
        if duration > min(90, paid.max_clip_seconds):
            raise _error("INVALID_CLIP", "选区超过当前已验证的单次上限", 422)
        period = session.get(UsagePeriod, paid.usage_period_id)
        if period is None or period.user_id != user.id or period.entitlement_type != "pro_paid":
            raise _error("ENTITLEMENT_UNAVAILABLE", "用量记录暂不可用", 503)
        try:
            reservation = reserve_period(
                session,
                period,
                job_id,
                seconds,
                details={
                    "duration_seconds": duration,
                    "attempt": attempt,
                    "plan_version": paid.plan_version,
                    "max_clip_seconds": paid.max_clip_seconds,
                },
            )
        except UsageExceeded as error:
            raise HTTPException(
                429,
                headers={"Retry-After": str(error.retry_after)},
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "message": "本付费周期剩余秒数不足",
                    "retry_after": error.retry_after,
                },
            ) from error
    if session.scalar(
        select(TranscriptionJob.id)
        .where(
            TranscriptionJob.owner_user_id == user.id,
            TranscriptionJob.id != job_id,
            TranscriptionJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            TranscriptionJob.expires_at > datetime.now(UTC),
        )
        .limit(1)
    ):
        raise _error("ACTIVE_JOB_EXISTS", "请等待当前任务完成")
    return reservation


def usage_summary(session: Session, user: User, settings: Settings) -> dict[str, object]:
    if not settings.usage_enabled:
        return {"enabled": False, "plan": None}
    now = datetime.now(UTC)
    paid = (
        current_paid_period(
            session, user_id=user.id, environment=settings.billing_environment, now=now
        )
        if settings.paid_usage_enabled
        else None
    )
    if paid is not None:
        period = session.get(UsagePeriod, paid.usage_period_id)
        if period is None or period.user_id != user.id:
            raise _error("ENTITLEMENT_UNAVAILABLE", "用量记录暂不可用", 503)
        return {
            "enabled": True,
            "plan": "pro",
            "unit": "seconds",
            "state": paid.status,
            "limit": period.limit_units,
            "reserved": period.reserved_units,
            "used": period.consumed_units,
            "remaining": max(0, period.limit_units - period.reserved_units - period.consumed_units),
            "period_start": _as_utc(period.period_start),
            "period_end": _as_utc(period.period_end),
            "max_clip_seconds": min(90, paid.max_clip_seconds),
        }
    key, start, end = utc_month(now)
    period = session.scalar(
        select(UsagePeriod).where(
            UsagePeriod.user_id == user.id,
            UsagePeriod.entitlement_type == "free_month",
            UsagePeriod.period_key == key,
        )
    )
    reserved, used = (period.reserved_units, period.consumed_units) if period else (0, 0)
    limit = period.limit_units if period else settings.free_monthly_job_limit
    return {
        "enabled": True,
        "plan": "free",
        "unit": "jobs",
        "state": "active",
        "limit": limit,
        "reserved": reserved,
        "used": used,
        "remaining": max(0, limit - reserved - used),
        "period_start": start,
        "period_end": end,
        "max_clip_seconds": 90,
    }

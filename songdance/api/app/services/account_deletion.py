"""Durable account erasure after billing cancellation; identity tombstones remain."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AccountDeletion, JobStatus, TranscriptionJob, User
from app.observability import log_event
from app.services.account_deletion_billing import verify_stopped_billing
from app.services.billing import BillingMismatch
from app.services.creem_client import CreemClient
from app.services.entitlements import lock_usage_user
from app.services.lifecycle import delete_job_objects
from app.services.quota import JobQuota
from app.services.storage import ObjectStorage
from app.services.temp_cleanup import cleanup_job_temp_files
from app.services.usage import _as_utc, release_job_reservation
from app.settings import Settings


def assert_account_open(session: Session, user_id: str) -> None:
    user = session.get(User, user_id, populate_existing=True)
    if user is None or not user.active:
        raise HTTPException(403, detail={"code": "ACCOUNT_UNAVAILABLE"})
    if session.scalar(select(AccountDeletion.id).where(AccountDeletion.user_id == user_id)):
        raise HTTPException(409, detail={"code": "ACCOUNT_DELETION_PENDING"})


def deletion_response(row: AccountDeletion | None, enabled: bool) -> dict:
    return {
        "enabled": enabled,
        "deletion": None
        if row is None
        else {
            "id": row.id,
            "owner_id": row.user_id,
            "status": row.status,
            "phase": row.phase,
            "attempts": row.attempts,
            "requested_at": _as_utc(row.created_at).isoformat(),
            "completed_at": _as_utc(row.completed_at).isoformat() if row.completed_at else None,
            "error_code": row.error_code,
        },
    }


def request_account_deletion(
    session: Session, user: User, settings: Settings, authenticated_at: datetime | None
) -> AccountDeletion:
    lock_usage_user(session, user.id)
    row = session.scalar(select(AccountDeletion).where(AccountDeletion.user_id == user.id))
    if row is not None and row.status != "review":
        return row
    if row is None and not settings.account_deletion_enabled:
        raise HTTPException(503, detail={"code": "ACCOUNT_DELETION_DISABLED"})
    if (
        authenticated_at is None
        or not 0 <= (datetime.now(UTC) - _as_utc(authenticated_at)).total_seconds() <= 600
    ):
        raise HTTPException(403, detail={"code": "REAUTH_REQUIRED"})
    if row is None:
        assert_account_open(session, user.id)
        row = AccountDeletion(
            id=secrets.token_urlsafe(24),
            user_id=user.id,
            status="pending",
            phase="billing",
            attempts=0,
            auth_confirmed_at=authenticated_at,
            next_attempt_at=datetime.now(UTC),
        )
        session.add(row)
    else:
        row.status, row.error_code = "pending", None
        row.retry_failures = 0
        row.auth_confirmed_at = authenticated_at
        row.next_attempt_at = datetime.now(UTC)
    session.commit()
    session.refresh(row)
    return row


def _cleanup_account(
    session: Session,
    row: AccountDeletion,
    storage: ObjectStorage,
    settings: Settings,
    quota: JobQuota | None,
) -> bool:
    jobs = session.scalars(
        select(TranscriptionJob)
        .where(TranscriptionJob.owner_user_id == row.user_id)
        .order_by(TranscriptionJob.id)
        .limit(settings.cleanup_batch_size)
        .with_for_update()
    ).all()
    for job in jobs:
        job.error_code, job.error_message = "DELETE_REQUESTED", "正在删除账户临时任务"
        job.status = JobStatus.FAILED
        release_job_reservation(session, job, reason="account_deletion")
        session.flush()
        try:
            delete_job_objects(job, storage)
            if cleanup_job_temp_files(settings, job.id).failed:
                raise OSError("Account task files could not be removed")
            if quota:
                quota.complete(job.id)
        except Exception:
            # Preserve the failure fence and release after partial storage removal.
            job.error_code, job.error_message = "DELETE_FAILED", "账户文件删除将重试"
            return False
        session.delete(job)
    session.flush()
    if not session.scalar(
        select(TranscriptionJob.id).where(TranscriptionJob.owner_user_id == row.user_id).limit(1)
    ):
        user = session.get(User, row.user_id)
        user.email = None
        row.status, row.error_code = "completed", None
        row.completed_at = datetime.now(UTC)
    return True


def process_account_deletions(
    factory: sessionmaker[Session],
    storage: ObjectStorage,
    settings: Settings,
    provider: CreemClient | None = None,
    quota: JobQuota | None = None,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(UTC)
    with factory() as session:
        candidates = session.execute(
            select(AccountDeletion.id, AccountDeletion.user_id)
            .where(
                AccountDeletion.status.in_(["pending", "retry"]),
                AccountDeletion.next_attempt_at <= current,
            )
            .order_by(AccountDeletion.created_at)
            .limit(limit)
        ).all()
    handled = 0
    for identifier, user_id in candidates:
        with factory() as session:
            lock_usage_user(session, user_id)
            row = session.scalar(
                select(AccountDeletion)
                .where(
                    AccountDeletion.id == identifier,
                    AccountDeletion.status.in_(["pending", "retry"]),
                    AccountDeletion.next_attempt_at <= current,
                )
                .with_for_update(skip_locked=True)
            )
            if row is None:
                continue
            row.attempts += 1
            try:
                with session.begin_nested():
                    if row.phase == "billing":
                        verify_stopped_billing(session, row, provider)
                        # Persist the billing checkpoint before touching account data.
                        session.get(User, row.user_id).active = False
                        row.phase, row.status, row.error_code = "cleanup", "pending", None
                        row.retry_failures = 0
                        row.next_attempt_at = current
                    else:
                        complete = _cleanup_account(session, row, storage, settings, quota)
                        if not complete:
                            _retry_deletion(row, current)
                        else:
                            row.retry_failures = 0
                            if row.status != "completed":
                                row.status, row.error_code, row.next_attempt_at = (
                                    "pending",
                                    None,
                                    current,
                                )
                    session.flush()
            except BillingMismatch as error:
                row.status = "review"
                row.error_code = (
                    str(error) if str(error).startswith("DELETION_") else "DELETION_BILLING_REVIEW"
                )
            except Exception:
                _retry_deletion(row, current)
            session.commit()
            log_event("account_deletion", status=row.status, phase=row.phase, attempt=row.attempts)
            handled += 1
    return handled


def _retry_deletion(row: AccountDeletion, current: datetime) -> None:
    row.retry_failures += 1
    row.status = "review" if row.retry_failures >= 8 else "retry"
    row.error_code = (
        "DELETION_BILLING_RETRY" if row.phase == "billing" else "DELETION_CLEANUP_RETRY"
    )
    row.next_attempt_at = current + timedelta(
        seconds=min(3600, 30 * 2 ** min(row.retry_failures, 7))
    )

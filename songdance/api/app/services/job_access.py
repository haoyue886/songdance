import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import TranscriptionJob, User


def get_available_job(
    session: Session, job_id: str, *, for_update: bool = False
) -> TranscriptionJob:
    statement = (
        select(TranscriptionJob)
        .where(TranscriptionJob.id == job_id)
        .options(
            selectinload(TranscriptionJob.source_asset),
            selectinload(TranscriptionJob.result),
            selectinload(TranscriptionJob.artifacts),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    job = session.scalar(statement)
    if job is None:
        raise HTTPException(status_code=404, detail="Task unavailable")
    if job.error_code == "DELETE_REQUESTED":
        raise HTTPException(status_code=404, detail="Task unavailable")
    expires_at = job.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=404, detail="Task unavailable")
    return job


def new_guest_secret() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


def has_guest_access(job: TranscriptionJob, request: Request) -> bool:
    token = request.headers.get("x-job-access", "")
    return bool(
        job.guest_secret_hash
        and 20 <= len(token) <= 128
        and secrets.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(), job.guest_secret_hash
        )
    )


def get_accessible_job(
    session: Session,
    job_id: str,
    request: Request,
    user: User | None,
    *,
    for_update: bool = False,
) -> TranscriptionJob:
    job = get_available_job(session, job_id, for_update=for_update)
    if job.owner_user_id:
        if user is None or user.id != job.owner_user_id:
            raise HTTPException(status_code=404, detail="Task unavailable")
    elif job.guest_secret_hash and not has_guest_access(job, request):
        raise HTTPException(status_code=404, detail="Task unavailable")
    return job

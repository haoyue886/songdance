from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import TranscriptionJob


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

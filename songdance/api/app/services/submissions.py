import hashlib
import json
import re
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobSubmission, TranscriptionJob, User
from app.services.entitlements import lock_usage_user
from app.services.job_access import get_available_job


def validate_submission_key(value: str | None, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value):
        raise HTTPException(422, detail={"code": "IDEMPOTENCY_KEY_REQUIRED"})
    return value


def submission_fingerprint(**fields: object) -> str:
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def replay_submission(
    session: Session,
    user: User,
    key: str,
    fingerprint: str,
    operation: str,
) -> TranscriptionJob | None:
    # Also locks the first insert when there isn't a submission row yet.
    lock_usage_user(session, user.id)
    row = session.scalar(
        select(JobSubmission).where(
            JobSubmission.user_id == user.id,
            JobSubmission.submission_key == key,
        )
    )
    if row is None:
        return None
    if row.fingerprint != fingerprint or row.operation != operation:
        raise HTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})
    job = session.get(TranscriptionJob, row.job_id)
    if job is None or job.owner_user_id != user.id:
        raise HTTPException(410, detail={"code": "SUBMISSION_EXPIRED"})
    try:
        return get_available_job(session, job.id)
    except HTTPException as error:
        if error.status_code == 404:
            raise HTTPException(410, detail={"code": "SUBMISSION_EXPIRED"}) from error
        raise


def record_submission(
    session: Session,
    user: User,
    key: str,
    fingerprint: str,
    job: TranscriptionJob,
    operation: str,
) -> None:
    session.add(
        JobSubmission(
            id=secrets.token_urlsafe(24),
            user_id=user.id,
            submission_key=key,
            fingerprint=fingerprint,
            job_id=job.id,
            attempt=job.attempt_count,
            operation=operation,
        )
    )

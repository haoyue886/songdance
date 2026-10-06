"""DB outbox: upload -> pending -> published/running -> terminal.

Every transition locks the job before the outbox; no external queue result can
commit or delete the source intent. RQ publishing is idempotent by job + attempt.
"""

import hashlib
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import JobDispatch, JobStage, JobStatus, TranscriptionJob
from app.observability import log_event
from app.services.analytics import hash_job_id
from app.services.queue import JobQueue
from app.services.quota import JobQuota
from app.services.storage import ObjectStorage
from app.services.transcription_persistence import DELETE_ERROR_CODES, locked_job
from app.services.usage import _as_utc, release_job_reservation
from app.settings import Settings

OPEN = {"uploading", "pending", "published", "running"}


def add_dispatch(
    session: Session, job: TranscriptionJob, settings: Settings, *, uploading: bool
) -> None:
    now = datetime.now(UTC)
    session.add(
        JobDispatch(
            id=secrets.token_urlsafe(24),
            job_id=job.id,
            attempt=job.attempt_count,
            status="uploading" if uploading else "pending",
            publish_attempts=0,
            next_attempt_at=now
            + timedelta(seconds=settings.upload_intent_timeout_seconds if uploading else 0),
            deadline_at=now
            + timedelta(
                seconds=settings.upload_intent_timeout_seconds
                if uploading
                else settings.dispatch_wait_seconds
            ),
        )
    )


def ready_dispatch(session: Session, job: TranscriptionJob, settings: Settings) -> None:
    row = session.scalar(
        select(JobDispatch)
        .where(
            JobDispatch.job_id == job.id,
            JobDispatch.attempt == job.attempt_count,
        )
        .with_for_update()
    )
    if row is None or row.status != "uploading" or job.error_code in DELETE_ERROR_CODES:
        raise ValueError("Upload intent is no longer active")
    row.status = "pending"
    row.next_attempt_at = datetime.now(UTC)
    row.deadline_at = row.next_attempt_at + timedelta(seconds=settings.dispatch_wait_seconds)
    job.stage = JobStage.QUEUED


def begin_dispatch_run(session: Session, job: TranscriptionJob, settings: Settings) -> bool:
    if not job.dispatch_managed:
        return True
    row = session.scalar(
        select(JobDispatch)
        .where(
            JobDispatch.job_id == job.id,
            JobDispatch.attempt == job.attempt_count,
        )
        .with_for_update()
    )
    if (
        row is None
        or row.status not in {"pending", "published", "running"}
        or job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}
        or job.error_code in DELETE_ERROR_CODES
        or _as_utc(job.expires_at) <= datetime.now(UTC)
    ):
        return False
    row.status = "running"
    # RQ uses a 900-second hard timeout; allow its final failure callback to run first.
    row.deadline_at = datetime.now(UTC) + timedelta(seconds=960)
    row.next_attempt_at = row.deadline_at
    session.commit()
    return True


def _source_matches(job: TranscriptionJob, settings: Settings, storage: ObjectStorage) -> bool:
    if job.source_asset is None or not storage.exists(job.source_asset.storage_key):
        return False
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dispatch-", dir=settings.temp_path) as workdir:
        path = Path(workdir) / "source.wav"
        storage.download_file(job.source_asset.storage_key, path)
        if path.stat().st_size != job.source_asset.size_bytes:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == job.source_asset.sha256


def _fail(session: Session, job: TranscriptionJob, row: JobDispatch, code: str) -> None:
    # Terminal status fences every persistence/artifact path before releasing quota.
    job.status = JobStatus.FAILED
    job.error_code = code
    job.error_message = "任务未能完成，请稍后重试"
    release_job_reservation(session, job, reason=code)
    row.status = "failed"
    row.error_code = code


def dispatch_one(
    factory: sessionmaker[Session],
    job_id: str,
    attempt: int,
    settings: Settings,
    queue: JobQueue,
    storage: ObjectStorage,
    quota: JobQuota,
    *,
    now: datetime | None = None,
) -> bool:
    clock = now or datetime.now(UTC)
    with factory() as session:
        job = locked_job(session, job_id)
        row = session.scalar(
            select(JobDispatch)
            .where(JobDispatch.job_id == job_id, JobDispatch.attempt == attempt)
            .with_for_update()
        )
        if row is None or row.status not in OPEN or _as_utc(row.next_attempt_at) > clock:
            return False
        if job is None or job.attempt_count != attempt or job.error_code in DELETE_ERROR_CODES:
            row.status = "canceled"
            session.commit()
            # Never release a newer attempt's quota by its reused job ID.
            return True
        if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
            row.status = "finished"
        elif _as_utc(job.expires_at) <= clock:
            _fail(session, job, row, "TASK_EXPIRED")
        elif row.status == "uploading":
            try:
                matched = _source_matches(job, settings, storage)
            except Exception:
                # An unavailable storage service is not proof that the upload is absent.
                row.next_attempt_at = clock + timedelta(seconds=30)
                row.error_code = "STORAGE_UNAVAILABLE"
                session.commit()
                return True
            if matched:
                ready_dispatch(session, job, settings)
                row.next_attempt_at = clock
                row.deadline_at = clock + timedelta(seconds=settings.dispatch_wait_seconds)
            else:
                _fail(session, job, row, "UPLOAD_INCOMPLETE")
        elif _as_utc(row.deadline_at) <= clock:
            _fail(
                session,
                job,
                row,
                "DISPATCH_TIMEOUT" if job.status == JobStatus.QUEUED else "WORKER_LOST",
            )
        elif job.status == JobStatus.RUNNING:
            # A lost Redis ACK must not cause a second execution or source deletion.
            row.status = "running"
            row.next_attempt_at = row.deadline_at
        if row.status in {"pending", "published"}:
            try:
                queue.enqueue_unique(job_id, attempt)
            except Exception:
                row.publish_attempts += 1
                row.error_code = "QUEUE_UNAVAILABLE"
                row.next_attempt_at = clock + timedelta(
                    seconds=min(60, 2 ** min(row.publish_attempts, 6))
                )
                log_event("dispatch_retry", job_id_hash=hash_job_id(job_id, settings))
            else:
                row.status = "published"
                row.publish_attempts += 1
                row.error_code = None
                # Re-publish missing Redis jobs; RQ unique enqueue is safe if already present.
                row.next_attempt_at = clock + timedelta(seconds=30)
        if row.status in {"failed", "finished"}:
            try:
                quota.complete(job_id)
            except Exception:
                log_event("quota_release_failed", job_id_hash=hash_job_id(job_id, settings))
        session.commit()
        return True


def dispatch_pending(
    factory: sessionmaker[Session],
    settings: Settings,
    queue: JobQueue,
    storage: ObjectStorage,
    quota: JobQuota,
    *,
    now: datetime | None = None,
) -> int:
    clock = now or datetime.now(UTC)
    with factory() as session:
        rows = session.execute(
            select(JobDispatch.job_id, JobDispatch.attempt)
            .where(
                JobDispatch.status.in_(OPEN),
                JobDispatch.next_attempt_at <= clock,
            )
            .order_by(JobDispatch.next_attempt_at)
            .limit(settings.cleanup_batch_size)
        ).all()
    processed = 0
    for job_id, attempt in rows:
        try:
            processed += dispatch_one(
                factory, job_id, attempt, settings, queue, storage, quota, now=clock
            )
        except Exception:
            log_event("dispatch_cycle_item_failed", job_id_hash=hash_job_id(job_id, settings))
    return processed

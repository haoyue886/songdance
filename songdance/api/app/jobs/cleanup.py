import argparse
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import create_db_engine, create_session_factory
from app.models import JobStage, JobStatus, TranscriptionJob
from app.observability import configure_logging, log_event
from app.services.analytics import hash_job_id
from app.services.lifecycle import delete_job_objects
from app.services.quota import JobQuota, create_job_quota
from app.services.storage import ObjectStorage, create_storage
from app.services.temp_cleanup import cleanup_job_temp_files, cleanup_stale_temp_files
from app.services.transcription_persistence import locked_job
from app.settings import Settings, get_settings


@dataclass(frozen=True)
class CleanupResult:
    deleted: int
    failed: int
    temp_deleted: int = 0
    temp_failed: int = 0


def cleanup_expired_jobs(
    factory: sessionmaker[Session],
    storage: ObjectStorage,
    settings: Settings,
    *,
    now: datetime | None = None,
    job_quota: JobQuota | None = None,
) -> CleanupResult:
    cutoff = now or datetime.now(UTC)
    stale_upload_cutoff = cutoff - timedelta(seconds=settings.upload_intent_timeout_seconds)
    with factory() as session:
        job_ids = list(
            session.scalars(
                select(TranscriptionJob.id)
                .where(
                    or_(
                        TranscriptionJob.expires_at <= cutoff,
                        and_(
                            TranscriptionJob.stage == JobStage.UPLOAD,
                            TranscriptionJob.updated_at <= stale_upload_cutoff,
                        ),
                    )
                )
                .order_by(TranscriptionJob.updated_at)
                .limit(settings.cleanup_batch_size)
            ).all()
        )
    deleted = 0
    failed = 0
    job_temp_deleted = 0
    job_temp_failed = 0
    for job_id in job_ids:
        with factory() as session:
            job = locked_job(session, job_id)
            if job is None:
                continue
            stale_upload = (
                job.stage == JobStage.UPLOAD and _as_utc(job.updated_at) <= stale_upload_cutoff
            )
            if _as_utc(job.expires_at) > cutoff and not stale_upload:
                continue
            job_hash = hash_job_id(job.id, settings)
            job.error_code = "DELETE_REQUESTED"
            job.error_message = "正在删除过期音频和任务数据"
            session.flush()
            try:
                delete_job_objects(job, storage)
                job_temp = cleanup_job_temp_files(settings, job.id)
                job_temp_deleted += job_temp.deleted
                job_temp_failed += job_temp.failed
                if job_temp.failed:
                    raise OSError("job temporary files could not be removed")
            except Exception:
                job.status = JobStatus.FAILED
                job.error_code = "DELETE_FAILED"
                job.error_message = "部分过期文件删除失败，将自动重试"
                session.commit()
                failed += 1
                log_event("expired_job_cleanup_failed", job_id_hash=job_hash)
                if stale_upload:
                    _release_quota(job_quota, settings, job.id)
                continue
            session.delete(job)
            session.commit()
            _release_quota(job_quota, settings, job.id)
            deleted += 1
            log_event(
                "stale_upload_intent_deleted" if stale_upload else "expired_job_deleted",
                job_id_hash=job_hash,
            )
    stale_temp = cleanup_stale_temp_files(settings, now=cutoff)
    return CleanupResult(
        deleted=deleted,
        failed=failed,
        temp_deleted=job_temp_deleted + stale_temp.deleted,
        temp_failed=job_temp_failed + stale_temp.failed,
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _release_quota(job_quota: JobQuota | None, settings: Settings, job_id: str) -> None:
    if job_quota is None:
        return
    try:
        job_quota.complete(job_id)
    except Exception:
        log_event("quota_release_failed", job_id_hash=hash_job_id(job_id, settings))


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete expired SongDance jobs and objects")
    parser.add_argument("--loop", action="store_true", help="run continuously")
    args = parser.parse_args()
    configure_logging()
    settings = get_settings()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    storage = create_storage(settings)
    job_quota = create_job_quota(settings)
    try:
        while True:
            result = cleanup_expired_jobs(factory, storage, settings, job_quota=job_quota)
            log_event(
                "cleanup_cycle",
                deleted=result.deleted,
                failed=result.failed,
                temp_deleted=result.temp_deleted,
                temp_failed=result.temp_failed,
            )
            if not args.loop:
                break
            time.sleep(settings.cleanup_interval_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

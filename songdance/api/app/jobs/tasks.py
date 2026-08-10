from types import TracebackType

from redis import Redis
from rq import get_current_job
from rq.job import Job
from rq.timeouts import JobTimeoutException
from sqlalchemy.orm import Session

from app.database import create_db_engine, create_session_factory
from app.models import JobStatus, TranscriptionJob
from app.observability import log_event
from app.services.analytics import hash_job_id, record_terminal_event
from app.services.lifecycle import delete_known_job_objects
from app.services.quota import create_job_quota
from app.services.storage import create_storage
from app.services.transcription import run_transcription_job
from app.services.transcription_persistence import DELETE_ERROR_CODES, locked_job
from app.settings import Settings, get_settings


def verify_source_job(job_id: str, attempt: int = 1) -> None:
    rq_job = get_current_job()
    if rq_job is not None:
        count = rq_job.meta.get("worker_execution_count", 0)
        rq_job.meta["worker_execution_count"] = count + 1 if isinstance(count, int) else 1
        rq_job.save_meta()
    settings = get_settings()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    storage = create_storage(settings)
    try:
        run_transcription_job(job_id, settings, factory, storage, attempt=attempt)
        with factory() as session:
            job = session.get(TranscriptionJob, job_id)
            if job is None:
                delete_known_job_objects(job_id, storage)
            if job is None or job.attempt_count != attempt:
                return
        record_terminal_event(factory, settings, job_id)
        _complete_quota(settings, job_id)
    finally:
        engine.dispose()


def _fail_job(session: Session, job_id: str, code: str, message: str) -> None:
    job = locked_job(session, job_id)
    if job is None:
        return
    if job.error_code in DELETE_ERROR_CODES:
        return
    job.status = JobStatus.FAILED
    job.error_code = code
    job.error_message = message
    session.commit()


def mark_job_failed(
    rq_job: Job,
    _connection: Redis,
    _exception_type: type[BaseException],
    _exception_value: BaseException,
    _traceback: TracebackType | None,
) -> None:
    if rq_job.should_retry:
        return
    job_id = rq_job.meta.get("transcription_job_id")
    attempt = rq_job.meta.get("attempt", 1)
    if not isinstance(job_id, str) or not isinstance(attempt, int):
        return

    settings = get_settings()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            job = session.get(TranscriptionJob, job_id)
            if job is None or job.attempt_count != attempt:
                return
            code, message = failure_details(_exception_type)
            _fail_job(session, job_id, code, message)
        record_terminal_event(factory, settings, job_id)
        _complete_quota(settings, job_id)
    finally:
        engine.dispose()


def failure_details(exception_type: type[BaseException]) -> tuple[str, str]:
    if issubclass(exception_type, JobTimeoutException):
        return "TRANSCRIPTION_TIMEOUT", "任务处理超时，请缩短片段后重试"
    return "WORKER_FAILED", "任务处理失败，请重试"


def _complete_quota(settings: Settings, job_id: str) -> None:
    try:
        create_job_quota(settings).complete(job_id)
    except Exception:
        log_event("quota_release_failed", job_id_hash=hash_job_id(job_id, settings))

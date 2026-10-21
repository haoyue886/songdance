import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_session
from app.models import (
    GuestSubmission,
    JobStage,
    JobStatus,
    JobSubmission,
    SourceAsset,
    TranscriptionJob,
    User,
)
from app.observability import log_event
from app.schemas import JobResponse
from app.services.analytics import hash_job_id, record_event
from app.services.audio_validation import (
    MAX_AUDIO_BYTES,
    AudioValidationError,
    audio_extension,
    extract_clip_to_wav,
    validate_audio_file,
    validate_clip,
)
from app.services.auth import optional_user
from app.services.dispatch import add_dispatch
from app.services.durable_jobs import create_durable_job, try_dispatch
from app.services.entitlements import ensure_no_active_job, lock_usage_user, reserve_job
from app.services.guest_usage import (
    record_guest_submission,
    replay_guest,
    reserve_trial,
    settle_guest,
    visitor_id,
)
from app.services.job_access import get_accessible_job, get_available_job, new_guest_secret
from app.services.lifecycle import delete_job_objects, remove_failed_upload_intent
from app.services.paid_periods import current_paid_period
from app.services.queue import JobQueue
from app.services.quota import JobQuota, QuotaExceeded, client_quota_key
from app.services.storage import ObjectStorage
from app.services.submissions import (
    record_submission,
    replay_submission,
    submission_fingerprint,
    validate_submission_key,
)
from app.services.temp_cleanup import cleanup_job_temp_files
from app.services.usage import (
    UsageExceeded,
    release_job_reservation,
    usage_http_error,
)
from app.settings import Settings

router = APIRouter(prefix="/jobs", tags=["jobs"])
CHUNK_SIZE = 1024 * 1024


def _storage(request: Request) -> ObjectStorage:
    return request.app.state.storage


def _queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _quota(request: Request) -> JobQuota:
    return request.app.state.job_quota


def _reserve_quota(request: Request, job_id: str, user: User | None = None) -> None:
    try:
        settings = _settings(request)
        paid_access = False
        if settings.paid_usage_enabled and user is not None:
            with request.app.state.session_factory() as quota_session:
                paid = current_paid_period(
                    quota_session, user_id=user.id, environment=settings.billing_environment
                )
                paid_access = paid is not None and paid.status == "active"
        _quota(request).reserve(job_id, client_quota_key(request, settings), paid=paid_access)
    except QuotaExceeded as error:
        raise HTTPException(
            status_code=429,
            headers={"Retry-After": str(error.retry_after)},
            detail={
                "code": error.code,
                "message": error.message,
                "retry_after": error.retry_after,
            },
        ) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Capacity service is unavailable") from error


def _cancel_quota(request: Request, job_id: str) -> None:
    try:
        _quota(request).cancel(job_id)
    except Exception:
        log_event(
            "quota_cancel_failed",
            job_id_hash=hash_job_id(job_id, _settings(request)),
        )


def _complete_quota(request: Request, job_id: str) -> None:
    try:
        _quota(request).complete(job_id)
    except Exception:
        log_event(
            "quota_release_failed",
            job_id_hash=hash_job_id(job_id, _settings(request)),
        )


async def _write_upload(upload: UploadFile, destination: Path) -> int:
    size = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(CHUNK_SIZE):
            size += len(chunk)
            if size > MAX_AUDIO_BYTES:
                raise AudioValidationError("FILE_TOO_LARGE", "文件超过 25 MB")
            output.write(chunk)
    if size == 0:
        raise AudioValidationError("EMPTY_FILE", "文件是空的")
    return size


def _fingerprint(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    request: Request,
    audio_file: Annotated[UploadFile, File()],
    start_sec: Annotated[float, Form()],
    end_sec: Annotated[float, Form()],
    rights_confirmed: Annotated[bool, Form()],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User | None, Depends(optional_user)],
) -> JobResponse:
    if not rights_confirmed:
        raise HTTPException(status_code=422, detail="Content rights confirmation is required")
    original_filename = audio_file.filename or ""
    filename = Path(original_filename).name
    if not filename:
        raise HTTPException(status_code=422, detail="A file name is required")
    if (
        filename != original_filename
        or len(filename) > 255
        or "/" in original_filename
        or "\\" in original_filename
        or any(ord(character) < 32 for character in filename)
    ):
        raise HTTPException(status_code=422, detail="The file name is not allowed")

    settings = _settings(request)
    key = request.headers.get("Idempotency-Key")
    old_submission = (
        user is not None
        and key is not None
        and session.scalar(
            select(JobSubmission.id).where(
                JobSubmission.user_id == user.id, JobSubmission.submission_key == key
            )
        )
    )
    old_guest_submission = False
    visitor_token = request.headers.get("X-Visitor-Token")
    if user is None and key and visitor_token and not settings.guest_usage_enabled:
        # Keep accepted visitor submissions recoverable while draining the feature.
        # Retain the original secret for as long as these records can be replayed.
        if not settings.guest_signing_secret.get_secret_value():
            raise HTTPException(503, detail={"code": "GUEST_USAGE_DISABLED"})
        trial_id = visitor_id(settings, visitor_token)
        old_guest_submission = (
            session.scalar(
                select(GuestSubmission.id).where(
                    GuestSubmission.trial_id == trial_id,
                    GuestSubmission.submission_key == key,
                )
            )
            is not None
        )
    if (
        settings.reliable_queue_enabled
        or settings.guest_usage_enabled
        or old_submission
        or old_guest_submission
    ):
        return await create_durable_job(
            request,
            session,
            user,
            audio_file,
            start_sec,
            end_sec,
            filename,
            guest_replay=old_guest_submission,
        )
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    temp_path = settings.temp_path / f"{secrets.token_hex(16)}.{audio_extension(filename)}"
    clip_path = settings.temp_path / f"{secrets.token_hex(16)}.wav"
    storage = _storage(request)
    storage_key: str | None = None
    job_id = secrets.token_urlsafe(24)
    guest_token, guest_hash = (
        new_guest_secret() if settings.auth_enabled and user is None else (None, None)
    )
    reserved = False
    intent_committed = False
    try:
        _reserve_quota(request, job_id, user)
        reserved = True
        await _write_upload(audio_file, temp_path)
        validated = await run_in_threadpool(
            validate_audio_file, temp_path, filename, audio_file.content_type
        )
        validate_clip(start_sec, end_sec, validated.duration)
        clipped = await run_in_threadpool(
            extract_clip_to_wav, temp_path, clip_path, start_sec, end_sec
        )
        size_bytes, sha256 = _fingerprint(clip_path)
        storage_key = f"jobs/{job_id}/source.wav"

        now = datetime.now(UTC)
        job = TranscriptionJob(
            id=job_id,
            owner_user_id=user.id if user else None,
            guest_secret_hash=guest_hash,
            status=JobStatus.QUEUED,
            stage=JobStage.UPLOAD,
            source_type="upload",
            start_sec=start_sec,
            end_sec=end_sec,
            attempt_count=1,
            expires_at=now + timedelta(hours=24),
        )
        if user is not None:
            from app.services.account_deletion import assert_account_open

            lock_usage_user(session, user.id)
            assert_account_open(session, user.id)
        if settings.usage_enabled:
            if user is None and end_sec - start_sec > 30:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "GUEST_CLIP_LIMIT", "message": "游客体验最多 30 秒"},
                )
            if user is not None:
                try:
                    job.usage_reservation_id = reserve_job(
                        session, user, job_id, settings, duration=clipped.duration
                    )
                except UsageExceeded as error:
                    raise usage_http_error(error) from error
        job.source_asset = SourceAsset(
            id=secrets.token_urlsafe(24),
            storage_key=storage_key,
            mime_type=clipped.mime_type,
            size_bytes=size_bytes,
            duration_sec=clipped.duration,
            sha256=sha256,
            original_filename=filename,
        )
        session.add(job)
        session.commit()
        intent_committed = True
        # Cleanup must wait for this PUT or remove the intent before it starts.
        current_job = get_available_job(session, job.id, for_update=True)
        if current_job.stage != JobStage.UPLOAD or current_job.status != JobStatus.QUEUED:
            raise HTTPException(409, detail={"code": "UPLOAD_NO_LONGER_ACTIVE"})
        storage.put_file(storage_key, clip_path, clipped.mime_type)
        try:
            _queue(request).enqueue(job.id, job.attempt_count)
        except Exception as error:
            raise HTTPException(status_code=503, detail="Task queue is unavailable") from error
        session.expire(job)
        current_job = get_available_job(session, job.id, for_update=True)
        if current_job.stage == JobStage.UPLOAD:
            current_job.stage = JobStage.QUEUED
            session.commit()
        job = current_job
        try:
            record_event(
                session,
                settings,
                "transcription_submitted",
                job_id=job.id,
                properties={"source_type": "upload", "clip_seconds": clipped.duration},
            )
            session.commit()
        except Exception:
            session.rollback()
            log_event("analytics_write_failed", event_name="transcription_submitted")
        reserved = False
        return JobResponse.model_validate(get_available_job(session, job.id)).model_copy(
            update={"guest_access_token": guest_token}
        )
    except AudioValidationError as error:
        raise HTTPException(
            status_code=422, detail={"code": error.code, "message": error.message}
        ) from error
    except Exception:
        session.rollback()
        if intent_committed and storage_key:
            remove_failed_upload_intent(session, storage, job_id, storage_key)
        elif storage_key:
            storage.delete(storage_key)
        raise
    finally:
        if reserved:
            _cancel_quota(request, job_id)
        await audio_file.close()
        temp_path.unlink(missing_ok=True)
        clip_path.unlink(missing_ok=True)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User | None, Depends(optional_user)],
) -> JobResponse:
    return JobResponse.model_validate(get_accessible_job(session, job_id, request, user))


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User | None, Depends(optional_user)],
) -> JobResponse:
    if user is not None:
        lock_usage_user(session, user.id)
        from app.services.account_deletion import assert_account_open

        assert_account_open(session, user.id)
    key = request.headers.get("Idempotency-Key")
    fingerprint = submission_fingerprint(job_id=job_id)
    if key is not None and user is not None:
        validate_submission_key(key, True)
        previous = replay_submission(session, user, key, fingerprint, "retry")
        if previous is not None:
            return JobResponse.model_validate(previous)
    job = get_accessible_job(session, job_id, request, user, for_update=True)
    if job.dispatch_managed:
        validate_submission_key(key, user is not None)
    if job.guest_trial_id and user is None:
        validate_submission_key(key, True)
        previous = replay_guest(session, job.guest_trial_id, key, fingerprint, "retry")
        if previous is not None:
            return JobResponse.model_validate(previous)
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed tasks can be retried")
    if job.error_code == "DELETE_FAILED":
        raise HTTPException(status_code=409, detail="Task deletion must be retried")
    if job.error_code == "UPLOAD_INCOMPLETE":
        raise HTTPException(409, detail={"code": "UPLOAD_INCOMPLETE"})
    if job.attempt_count >= 3:
        raise HTTPException(status_code=409, detail="Retry limit reached")
    if job.guest_trial_id:
        if user is not None and request.app.state.settings.usage_enabled:
            ensure_no_active_job(session, user.id, job_id)
        settle_guest(session, job, False, "retry_failed_attempt")
        job.guest_reservation_id = reserve_trial(session, job.guest_trial_id, job_id)
    elif request.app.state.settings.usage_enabled and user is not None:
        try:
            if job.source_asset is None:
                raise HTTPException(409, detail="Source asset is unavailable")
            release_job_reservation(session, job, reason="retry_failed_attempt")
            job.usage_reservation_id = reserve_job(
                session,
                user,
                job_id,
                request.app.state.settings,
                duration=job.source_asset.duration_sec,
                attempt=job.attempt_count + 1,
            )
        except UsageExceeded as error:
            raise usage_http_error(error) from error
    _reserve_quota(request, job_id, user)
    job.attempt_count += 1
    job.status = JobStatus.QUEUED
    job.stage = JobStage.QUEUED
    job.error_code = None
    job.error_message = None
    if job.dispatch_managed:
        if user is not None and key is not None:
            record_submission(session, user, key, fingerprint, job, "retry")
        elif job.guest_trial_id and key:
            record_guest_submission(session, job.guest_trial_id, key, fingerprint, job.id, "retry")
        add_dispatch(session, job, request.app.state.settings, uploading=False)
    session.commit()
    if job.dispatch_managed:
        try_dispatch(request, job_id, job.attempt_count)
        session.expire_all()
        return JobResponse.model_validate(get_available_job(session, job_id))
    try:
        _queue(request).enqueue(job.id, job.attempt_count)
    except Exception as error:
        job.status = JobStatus.FAILED
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message = "任务队列暂时不可用"
        release_job_reservation(session, job, reason="queue_unavailable")
        session.commit()
        _cancel_quota(request, job_id)
        raise HTTPException(status_code=503, detail="Task queue is unavailable") from error
    return JobResponse.model_validate(get_available_job(session, job_id))


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[User | None, Depends(optional_user)],
) -> None:
    job = get_accessible_job(session, job_id, request, user, for_update=True)
    storage = _storage(request)
    previous_status = job.status
    job.error_code = "DELETE_REQUESTED"
    job.error_message = "正在删除音频和任务数据"
    release_job_reservation(session, job, reason="user_delete")
    session.commit()
    session.expire(job, ["artifacts", "source_asset"])
    try:
        delete_job_objects(job, storage)
        temp_result = cleanup_job_temp_files(_settings(request), job_id)
        if temp_result.failed:
            raise OSError("job temporary files could not be removed")
    except Exception as error:
        job.status = JobStatus.FAILED
        job.error_code = "DELETE_FAILED"
        job.error_message = "部分文件删除失败，请重试删除"
        release_job_reservation(session, job, reason="delete_failed")
        session.commit()
        raise HTTPException(status_code=503, detail="Task deletion is incomplete") from error
    try:
        record_event(
            session,
            _settings(request),
            "job_deleted",
            job_id=job_id,
            properties={"status": previous_status},
        )
    except Exception:
        log_event("analytics_write_failed", event_name="job_deleted")
    release_job_reservation(session, job, reason="user_delete")
    session.delete(job)
    session.commit()
    _complete_quota(request, job_id)

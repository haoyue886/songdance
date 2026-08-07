import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import JobStage, JobStatus, SourceAsset, TranscriptionJob
from app.observability import log_event
from app.schemas import JobResponse
from app.services.analytics import hash_job_id, record_event
from app.services.audio_validation import (
    MAX_AUDIO_BYTES,
    AudioValidationError,
    extract_clip_to_wav,
    validate_audio_file,
    validate_clip,
)
from app.services.job_access import get_available_job
from app.services.lifecycle import delete_job_objects, remove_failed_upload_intent
from app.services.queue import JobQueue
from app.services.quota import JobQuota, QuotaExceeded, client_quota_key
from app.services.storage import ObjectStorage
from app.services.temp_cleanup import cleanup_job_temp_files
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


def _reserve_quota(request: Request, job_id: str) -> None:
    try:
        _quota(request).reserve(job_id, client_quota_key(request, _settings(request)))
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
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    temp_path = settings.temp_path / f"{secrets.token_hex(16)}{Path(filename).suffix.lower()}"
    clip_path = settings.temp_path / f"{secrets.token_hex(16)}.wav"
    storage = _storage(request)
    storage_key: str | None = None
    job_id = secrets.token_urlsafe(24)
    reserved = False
    intent_committed = False
    try:
        _reserve_quota(request, job_id)
        reserved = True
        await _write_upload(audio_file, temp_path)
        validated = validate_audio_file(temp_path, filename, audio_file.content_type)
        validate_clip(start_sec, end_sec, validated.duration)
        clipped = extract_clip_to_wav(temp_path, clip_path, start_sec, end_sec)
        size_bytes, sha256 = _fingerprint(clip_path)
        storage_key = f"jobs/{job_id}/source.wav"

        now = datetime.now(UTC)
        job = TranscriptionJob(
            id=job_id,
            status=JobStatus.QUEUED,
            stage=JobStage.UPLOAD,
            source_type="upload",
            start_sec=start_sec,
            end_sec=end_sec,
            attempt_count=1,
            expires_at=now + timedelta(hours=24),
        )
        job.source_asset = SourceAsset(
            id=secrets.token_urlsafe(24),
            storage_key=storage_key,
            mime_type=clipped.mime_type,
            size_bytes=size_bytes,
            duration_sec=clipped.duration,
            sha256=sha256,
        )
        session.add(job)
        session.commit()
        intent_committed = True
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
        return JobResponse.model_validate(get_available_job(session, job.id))
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
def get_job(job_id: str, session: Annotated[Session, Depends(get_session)]) -> JobResponse:
    return JobResponse.model_validate(get_available_job(session, job_id))


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> JobResponse:
    job = get_available_job(session, job_id, for_update=True)
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed tasks can be retried")
    if job.error_code == "DELETE_FAILED":
        raise HTTPException(status_code=409, detail="Task deletion must be retried")
    if job.attempt_count >= 3:
        raise HTTPException(status_code=409, detail="Retry limit reached")
    _reserve_quota(request, job_id)
    job.attempt_count += 1
    job.status = JobStatus.QUEUED
    job.stage = JobStage.QUEUED
    job.error_code = None
    job.error_message = None
    session.commit()
    try:
        _queue(request).enqueue(job.id, job.attempt_count)
    except Exception as error:
        job.status = JobStatus.FAILED
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message = "任务队列暂时不可用"
        session.commit()
        _cancel_quota(request, job_id)
        raise HTTPException(status_code=503, detail="Task queue is unavailable") from error
    return JobResponse.model_validate(get_available_job(session, job_id))


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    job = get_available_job(session, job_id, for_update=True)
    storage = _storage(request)
    previous_status = job.status
    job.error_code = "DELETE_REQUESTED"
    job.error_message = "正在删除音频和任务数据"
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
    session.delete(job)
    session.commit()
    _complete_quota(request, job_id)

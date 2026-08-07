import hashlib
import secrets
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import JobStage, JobStatus, SourceAsset, TranscriptionJob
from app.observability import log_event
from app.pipeline.errors import PipelineError
from app.pipeline.youtube import download_youtube_clip, parse_youtube_video_id
from app.schemas import JobResponse, YoutubeConfigResponse, YoutubeJobRequest
from app.services.analytics import hash_job_id, record_event
from app.services.audio_validation import MAX_AUDIO_BYTES, AudioValidationError, validate_audio_file
from app.services.job_access import get_available_job
from app.services.lifecycle import remove_failed_upload_intent
from app.services.quota import QuotaExceeded, client_quota_key
from app.settings import Settings

router = APIRouter(prefix="/youtube", tags=["youtube"])
CHUNK_SIZE = 1024 * 1024


@router.get("/config", response_model=YoutubeConfigResponse)
def youtube_config(request: Request) -> YoutubeConfigResponse:
    return YoutubeConfigResponse(enabled=request.app.state.settings.youtube_enabled)


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_youtube_job(
    payload: YoutubeJobRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> JobResponse:
    settings = request.app.state.settings
    if not settings.youtube_enabled:
        raise _http_error(503, "YOUTUBE_DISABLED", "YouTube 导入暂不可用，请改用本地上传")
    if not payload.rights_confirmed:
        raise _http_error(422, "RIGHTS_REQUIRED", "必须确认拥有处理该内容所需的权利")
    clip_seconds = payload.end_sec - payload.start_sec
    if clip_seconds < 1 or clip_seconds > 90:
        raise _http_error(422, "INVALID_CLIP", "转录片段必须在 1 到 90 秒之间")
    try:
        video_id = parse_youtube_video_id(payload.url)
    except PipelineError as error:
        raise _pipeline_http_error(error) from error

    job_id = secrets.token_urlsafe(24)
    reserved = _reserve_quota(request, job_id)
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="youtube-", dir=settings.temp_path))
    source_path = workdir / "source.wav"
    storage_key = f"jobs/{job_id}/source.wav"
    intent_committed = False
    try:
        download_youtube_clip(
            video_id,
            payload.start_sec,
            payload.end_sec,
            source_path,
            settings.youtube_download_timeout_seconds,
        )
        if source_path.stat().st_size > MAX_AUDIO_BYTES:
            raise PipelineError("YOUTUBE_CLIP_TOO_LARGE", "所选音频片段过大，请缩短后重试")
        validated = validate_audio_file(source_path, source_path.name, "audio/wav")
        if abs(validated.duration - clip_seconds) > 0.5:
            raise PipelineError("YOUTUBE_CLIP_INVALID", "平台未返回所选片段，请改用本地上传")
        size_bytes, sha256 = _fingerprint(source_path)
        now = datetime.now(UTC)
        job = TranscriptionJob(
            id=job_id,
            status=JobStatus.QUEUED,
            stage=JobStage.UPLOAD,
            source_type="youtube",
            start_sec=payload.start_sec,
            end_sec=payload.end_sec,
            attempt_count=1,
            expires_at=now + timedelta(hours=24),
        )
        job.source_asset = SourceAsset(
            id=secrets.token_urlsafe(24),
            storage_key=storage_key,
            mime_type=validated.mime_type,
            size_bytes=size_bytes,
            duration_sec=validated.duration,
            sha256=sha256,
        )
        session.add(job)
        session.commit()
        intent_committed = True
        request.app.state.storage.put_file(storage_key, source_path, validated.mime_type)
        try:
            request.app.state.job_queue.enqueue(job.id, job.attempt_count)
        except Exception as error:
            raise _http_error(503, "QUEUE_UNAVAILABLE", "任务队列暂时不可用") from error
        session.expire(job)
        current_job = get_available_job(session, job.id, for_update=True)
        if current_job.stage == JobStage.UPLOAD:
            current_job.stage = JobStage.QUEUED
            session.commit()
        _record_submission(session, settings, current_job.id, clip_seconds)
        reserved = False
        return JobResponse.model_validate(get_available_job(session, current_job.id))
    except (PipelineError, AudioValidationError) as error:
        raise _pipeline_http_error(error) from error
    except Exception:
        session.rollback()
        if intent_committed:
            remove_failed_upload_intent(session, request.app.state.storage, job_id, storage_key)
        raise
    finally:
        if reserved:
            _cancel_quota(request, job_id)
        shutil.rmtree(workdir, ignore_errors=True)


def _reserve_quota(request: Request, job_id: str) -> bool:
    try:
        request.app.state.job_quota.reserve(
            job_id, client_quota_key(request, request.app.state.settings)
        )
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
        raise _http_error(503, "CAPACITY_UNAVAILABLE", "容量服务暂时不可用") from error
    return True


def _cancel_quota(request: Request, job_id: str) -> None:
    try:
        request.app.state.job_quota.cancel(job_id)
    except Exception:
        log_event(
            "quota_cancel_failed",
            job_id_hash=hash_job_id(job_id, request.app.state.settings),
        )


def _record_submission(
    session: Session, settings: Settings, job_id: str, clip_seconds: float
) -> None:
    try:
        record_event(
            session,
            settings,
            "transcription_submitted",
            job_id=job_id,
            properties={"source_type": "youtube", "clip_seconds": clip_seconds},
        )
        session.commit()
    except Exception:
        session.rollback()
        log_event("analytics_write_failed", event_name="transcription_submitted")


def _fingerprint(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _pipeline_http_error(error: PipelineError | AudioValidationError) -> HTTPException:
    unavailable = error.code not in {"YOUTUBE_URL_INVALID", "INVALID_CLIP"}
    return _http_error(503 if unavailable else 422, error.code, error.message)


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})

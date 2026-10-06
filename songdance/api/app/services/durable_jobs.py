import math
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models import GuestSubmission, JobStage, JobStatus, SourceAsset, TranscriptionJob, User
from app.observability import log_event
from app.schemas import JobResponse
from app.services.audio_validation import (
    AudioValidationError,
    audio_extension,
    extract_clip_to_wav,
    validate_audio_file,
    validate_clip,
)
from app.services.dispatch import add_dispatch, dispatch_one, ready_dispatch
from app.services.guest_usage import (
    lock_trial,
    record_guest_submission,
    replay_guest,
    reserve_guest_day,
    reserve_trial,
    visitor_id,
    visitor_job_secret,
)
from app.services.job_access import get_available_job, new_guest_secret
from app.services.quota import client_quota_key
from app.services.submissions import (
    record_submission,
    replay_submission,
    submission_fingerprint,
    validate_submission_key,
)
from app.services.usage import UsageExceeded, usage_http_error


def try_dispatch(request: Request, job_id: str, attempt: int) -> None:
    try:
        dispatch_one(
            request.app.state.session_factory,
            job_id,
            attempt,
            request.app.state.settings,
            request.app.state.job_queue,
            request.app.state.storage,
            request.app.state.job_quota,
        )
    except Exception:
        # Acceptance is already durable, including unknown queue outcomes.
        log_event("dispatch_deferred")


async def create_durable_job(
    request: Request,
    session: Session,
    user: User | None,
    audio_file: UploadFile,
    start_sec: float,
    end_sec: float,
    filename: str,
    *,
    guest_replay: bool = False,
) -> JobResponse:
    # Keep shared validation/quota behavior in the existing route module.
    from app.routes.jobs import _cancel_quota, _fingerprint, _reserve_quota, _write_upload
    from app.services.entitlements import reserve_job

    settings = request.app.state.settings
    guest_mode = user is None and (settings.guest_usage_enabled or guest_replay)
    key = validate_submission_key(
        request.headers.get("Idempotency-Key"), user is not None or guest_mode
    )
    trial_id = visitor_id(settings, request.headers.get("X-Visitor-Token")) if guest_mode else None
    storage = request.app.state.storage
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    temp = settings.temp_path / f"{secrets.token_hex(16)}.{audio_extension(filename)}"
    clip = settings.temp_path / f"{secrets.token_hex(16)}.wav"
    job_id = secrets.token_urlsafe(24)
    reserved = committed = False
    try:
        if not math.isfinite(start_sec) or not math.isfinite(end_sec):
            raise HTTPException(422, detail={"code": "INVALID_CLIP"})
        if trial_id:
            # Serialize first submissions before capacity admission, too. Waiting in
            # the pool lets the earlier request finish its asynchronous upload.
            await run_in_threadpool(lock_trial, session, trial_id)
        possible_replay = (
            trial_id
            and key
            and session.scalar(
                select(GuestSubmission.id).where(
                    GuestSubmission.trial_id == trial_id,
                    GuestSubmission.submission_key == key,
                )
            )
        )
        if user is None and not possible_replay:
            _reserve_quota(request, job_id, user)
            reserved = True
        await _write_upload(audio_file, temp)
        if settings.usage_enabled and user is None and end_sec - start_sec > 30:
            raise HTTPException(422, detail={"code": "GUEST_CLIP_LIMIT"})
        _, upload_hash = _fingerprint(temp)
        fingerprint = submission_fingerprint(
            source_hash=upload_hash, filename=filename, start_sec=start_sec, end_sec=end_sec
        )
        if user is not None and key is not None:
            previous = replay_submission(session, user, key, fingerprint, "create")
            if previous is not None:
                return JobResponse.model_validate(previous)
        if trial_id and key:
            previous = replay_guest(session, trial_id, key, fingerprint, "create")
            if previous is not None:
                token, _ = visitor_job_secret(settings, trial_id, previous.id)
                return JobResponse.model_validate(previous).model_copy(
                    update={"guest_access_token": token}
                )
        if not reserved:
            _reserve_quota(request, job_id, user)
            reserved = True
        guest_reservation = None
        if trial_id:
            guest_reservation = reserve_trial(session, trial_id, job_id)
            reserve_guest_day(session, settings, client_quota_key(request, settings), job_id)
        validated = validate_audio_file(temp, filename, audio_file.content_type)
        validate_clip(start_sec, end_sec, validated.duration)
        clipped = extract_clip_to_wav(temp, clip, start_sec, end_sec)
        size, digest = _fingerprint(clip)
        guest_token, guest_hash = (
            new_guest_secret() if settings.auth_enabled and user is None else (None, None)
        )
        if trial_id:
            guest_token, guest_hash = visitor_job_secret(settings, trial_id, job_id)
        job = TranscriptionJob(
            id=job_id,
            owner_user_id=user.id if user else None,
            guest_secret_hash=guest_hash,
            guest_trial_id=trial_id,
            guest_reservation_id=guest_reservation,
            dispatch_managed=True,
            status=JobStatus.QUEUED,
            stage=JobStage.UPLOAD,
            start_sec=start_sec,
            end_sec=end_sec,
            attempt_count=1,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        if settings.usage_enabled and user:
            job.usage_reservation_id = reserve_job(
                session, user, job.id, settings, duration=clipped.duration
            )
        if trial_id and key:
            record_guest_submission(session, trial_id, key, fingerprint, job.id, "create")
        job.source_asset = SourceAsset(
            id=secrets.token_urlsafe(24),
            storage_key=f"jobs/{job.id}/source.wav",
            mime_type=clipped.mime_type,
            size_bytes=size,
            duration_sec=clipped.duration,
            sha256=digest,
            original_filename=filename,
        )
        session.add(job)
        if user is not None and key is not None:
            record_submission(session, user, key, fingerprint, job, "create")
        add_dispatch(session, job, settings, uploading=True)
        session.commit()
        committed = True
        # Hold job lock during storage PUT; cleanup/recovery cannot race this writer.
        job = get_available_job(session, job_id, for_update=True)
        if job.stage != JobStage.UPLOAD or job.status != JobStatus.QUEUED:
            raise HTTPException(409, detail={"code": "UPLOAD_NO_LONGER_ACTIVE"})
        storage.put_file(job.source_asset.storage_key, clip, clipped.mime_type)
        ready_dispatch(session, job, settings)
        session.commit()
        try_dispatch(request, job_id, 1)
        session.expire_all()
        return JobResponse.model_validate(get_available_job(session, job_id)).model_copy(
            update={"guest_access_token": guest_token}
        )
    except UsageExceeded as error:
        session.rollback()
        raise usage_http_error(error) from error
    except AudioValidationError as error:
        session.rollback()
        raise HTTPException(422, detail={"code": error.code, "message": error.message}) from error
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise HTTPException(503, detail={"code": "SUBMISSION_UNAVAILABLE"}) from None
    finally:
        if reserved and not committed:
            # COMMIT may have reached PostgreSQL even if its response was lost.
            # Cancel capacity only after a separate read proves no accepted intent exists.
            try:
                with request.app.state.session_factory() as probe:
                    absent = probe.get(TranscriptionJob, job_id) is None
                if absent:
                    _cancel_quota(request, job_id)
            except Exception:
                log_event("submission_commit_unknown")
        await audio_file.close()
        temp.unlink(missing_ok=True)
        clip.unlink(missing_ok=True)

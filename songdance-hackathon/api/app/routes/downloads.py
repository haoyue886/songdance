import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.database import get_session
from app.observability import log_event
from app.schemas import DownloadUrlResponse
from app.services.analytics import record_event
from app.services.downloads import create_download_ticket, verify_download_ticket
from app.services.job_access import get_available_job
from app.services.storage import ObjectStorage
from app.settings import Settings

router = APIRouter(prefix="/jobs", tags=["downloads"])
ARTIFACT_FILENAMES = {
    "raw_midi": "raw.mid",
    "raw_timeline": "raw-timeline.json",
    "midi": "score.mid",
    "musicxml": "score.musicxml",
    "timeline": "timeline.json",
}


@router.get("/{job_id}/download-url/{file_type}", response_model=DownloadUrlResponse)
def get_download_url(
    job_id: str,
    file_type: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> DownloadUrlResponse:
    job = get_available_job(session, job_id)
    if file_type != "source":
        if file_type not in ARTIFACT_FILENAMES:
            raise HTTPException(status_code=404, detail="Artifact unavailable")
        artifact = next((item for item in job.artifacts if item.type == file_type), None)
        if artifact is None or artifact.status != "succeeded" or artifact.storage_key is None:
            raise HTTPException(status_code=404, detail="Artifact unavailable")
    ticket = create_download_ticket(job_id, file_type, _settings(request))
    return DownloadUrlResponse(path=ticket.path, expires_at=ticket.expires_at)


@router.get("/{job_id}/files/{file_type}")
def get_signed_file(
    job_id: str,
    file_type: str,
    expires: int,
    signature: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> FileResponse:
    if not verify_download_ticket(job_id, file_type, expires, signature, _settings(request)):
        raise HTTPException(status_code=403, detail="Download link is invalid or expired")
    job = get_available_job(session, job_id)
    if file_type == "source":
        return _download_response(
            request,
            job.source_asset.storage_key,
            job.source_asset.mime_type,
            "source.wav",
            inline=True,
        )
    if file_type not in ARTIFACT_FILENAMES:
        raise HTTPException(status_code=404, detail="Artifact unavailable")
    artifact = next((item for item in job.artifacts if item.type == file_type), None)
    if artifact is None or artifact.status != "succeeded" or artifact.storage_key is None:
        raise HTTPException(status_code=404, detail="Artifact unavailable")
    response = _download_response(
        request,
        artifact.storage_key,
        artifact.mime_type or "application/octet-stream",
        ARTIFACT_FILENAMES[file_type],
        inline=file_type in {"raw_timeline", "timeline"},
    )
    try:
        record_event(
            session,
            _settings(request),
            "artifact_served",
            job_id=job_id,
            properties={"artifact_type": file_type},
        )
        session.commit()
    except Exception:
        session.rollback()
        log_event("analytics_write_failed", event_name="artifact_served")
    return response


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _storage(request: Request) -> ObjectStorage:
    return request.app.state.storage


def _download_response(
    request: Request,
    storage_key: str,
    media_type: str,
    filename: str,
    *,
    inline: bool = False,
) -> FileResponse:
    download_dir = _settings(request).temp_path / "downloads"
    destination = download_dir / f"{secrets.token_hex(16)}{Path(filename).suffix}"
    try:
        _storage(request).download_file(storage_key, destination)
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=503, detail="Stored file is temporarily unavailable"
        ) from error
    return FileResponse(
        destination,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline" if inline else "attachment",
        background=BackgroundTask(destination.unlink, missing_ok=True),
    )

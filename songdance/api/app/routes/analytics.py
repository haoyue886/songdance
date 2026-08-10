from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas.analytics import AnalyticsEventCreate
from app.services.analytics import (
    hash_job_id,
    record_event,
    validate_client_event,
)
from app.services.event_quota import EventQuotaExceeded
from app.services.job_access import get_available_job
from app.services.quota import client_quota_key

router = APIRouter(prefix="/events", tags=["analytics"])


def _reserve_event(request: Request, job_key: str) -> None:
    try:
        request.app.state.job_quota.reserve_event(
            job_key,
            client_quota_key(request, request.app.state.settings),
        )
    except EventQuotaExceeded as error:
        raise HTTPException(
            status_code=429,
            headers={"Retry-After": str(error.retry_after)},
            detail={"code": error.code, "message": error.message},
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=503, detail="Event capacity service is unavailable"
        ) from error


@router.post("/upload-started", status_code=status.HTTP_202_ACCEPTED)
def create_upload_started_event(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    client_key = client_quota_key(request, request.app.state.settings)
    _reserve_event(request, f"upload:{client_key}")
    record_event(session, request.app.state.settings, "upload_started")
    session.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_event(
    payload: AnalyticsEventCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        properties = validate_client_event(payload.event_name, payload.properties)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    get_available_job(session, payload.job_id)
    job_id_hash = hash_job_id(payload.job_id, request.app.state.settings)
    _reserve_event(request, job_id_hash)
    record_event(
        session,
        request.app.state.settings,
        payload.event_name,
        job_id=payload.job_id,
        properties=properties,
    )
    session.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)

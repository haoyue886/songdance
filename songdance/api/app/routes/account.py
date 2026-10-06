from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import TranscriptionJob, User
from app.schemas import JobResponse
from app.services.auth import required_user
from app.services.billing import billing_state
from app.services.entitlements import usage_summary
from app.services.job_access import get_available_job, has_guest_access

router = APIRouter(tags=["account"])


@router.get("/billing/me")
def billing_me(
    request: Request,
    response: Response,
    user: Annotated[User, Depends(required_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    response.headers["Cache-Control"] = "private, no-store"
    result = usage_summary(session, user, request.app.state.settings)
    if request.app.state.settings.creem_enabled:
        result.update(billing_state(session, user.id))
    return result


@router.get("/me")
def me(response: Response, user: Annotated[User, Depends(required_user)]) -> dict[str, str | None]:
    response.headers["Cache-Control"] = "private, no-store"
    return {"id": user.id, "email": user.email}


@router.post("/jobs/{job_id}/claim", response_model=JobResponse)
def claim_job(
    job_id: str,
    request: Request,
    user: Annotated[User, Depends(required_user)],
    session: Annotated[Session, Depends(get_session)],
) -> JobResponse:
    job = get_available_job(session, job_id, for_update=True)
    if job.owner_user_id == user.id:
        return JobResponse.model_validate(job)
    if job.owner_user_id is not None or not has_guest_access(job, request):
        raise HTTPException(status_code=404, detail="Task unavailable")
    result = session.execute(
        update(TranscriptionJob)
        .where(
            TranscriptionJob.id == job_id,
            TranscriptionJob.owner_user_id.is_(None),
            TranscriptionJob.guest_secret_hash == job.guest_secret_hash,
        )
        .values(owner_user_id=user.id, guest_secret_hash=None)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=409, detail="Task could not be claimed")
    session.commit()
    session.expire_all()
    return JobResponse.model_validate(get_available_job(session, job_id))

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import AccountDeletion, TranscriptionJob, User
from app.schemas import JobResponse
from app.services.account_deletion import (
    assert_account_open,
    deletion_response,
    request_account_deletion,
)
from app.services.auth import account_status_user, required_user
from app.services.billing import billing_state
from app.services.entitlements import lock_usage_user, usage_summary
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
    if result.get("enabled"):
        result["owner_id"] = user.id
    if request.app.state.settings.creem_enabled:
        result.update(billing_state(session, user.id))
        result["owner_id"] = user.id
    return result


@router.get("/me")
def me(
    request: Request,
    response: Response,
    user: Annotated[User, Depends(account_status_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    data = _deletion_status(session, request, user)
    return {
        "id": user.id,
        "email": user.email,
        "account_deletion_enabled": data["enabled"],
        "deletion": data["deletion"],
    }


def _deletion_status(session: Session, request: Request, user: User) -> dict:
    row = session.scalar(select(AccountDeletion).where(AccountDeletion.user_id == user.id))
    return deletion_response(row, request.app.state.settings.account_deletion_enabled)


@router.get("/me/deletion")
def deletion_status(
    request: Request,
    response: Response,
    user: Annotated[User, Depends(account_status_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    return _deletion_status(session, request, user)


class DeleteAccountBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["DELETE"]


@router.delete("/me", status_code=202)
def delete_account(
    request: Request,
    response: Response,
    body: DeleteAccountBody,
    user: Annotated[User, Depends(account_status_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    if request.headers.get("origin") not in request.app.state.settings.cors_origin_list:
        raise HTTPException(403, detail={"code": "ORIGIN_REJECTED"})
    row = session.scalar(select(AccountDeletion).where(AccountDeletion.user_id == user.id))
    authenticated_at = None
    if row is None or row.status == "review":
        if row is None and not request.app.state.settings.account_deletion_enabled:
            raise HTTPException(503, detail={"code": "ACCOUNT_DELETION_DISABLED"})
        verifier = request.app.state.auth_verifier
        if not hasattr(verifier, "reauthenticated_at"):
            raise HTTPException(403, detail={"code": "REAUTH_REQUIRED"})
        authenticated_at = verifier.reauthenticated_at(request.state.verified_identity)
    row = request_account_deletion(session, user, request.app.state.settings, authenticated_at)
    return deletion_response(row, request.app.state.settings.account_deletion_enabled)


@router.post("/jobs/{job_id}/claim", response_model=JobResponse)
def claim_job(
    job_id: str,
    request: Request,
    user: Annotated[User, Depends(required_user)],
    session: Annotated[Session, Depends(get_session)],
) -> JobResponse:
    lock_usage_user(session, user.id)
    assert_account_open(session, user.id)
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

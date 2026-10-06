import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import User
from app.services.auth import required_user
from app.services.billing import BillingMismatch, create_checkout, create_portal
from app.services.billing_events import receive_event
from app.services.creem_client import CreemClient, CreemError

router = APIRouter(tags=["billing"])
MAX_WEBHOOK_BYTES = 256 * 1024


class EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _provider(request: Request) -> CreemClient:
    settings = request.app.state.settings
    if (
        not settings.creem_enabled
        or settings.billing_environment != "test"
        or settings.environment == "production"
    ):
        raise HTTPException(503, detail={"code": "BILLING_DISABLED"})
    return getattr(request.app.state, "creem_client", None) or CreemClient(settings)


def _write_origin(request: Request) -> None:
    if request.headers.get("origin") not in request.app.state.settings.cors_origin_list:
        raise HTTPException(403, detail={"code": "ORIGIN_REJECTED"})


@router.post("/billing/checkout")
def checkout(
    request: Request,
    response: Response,
    body: EmptyBody,
    user: Annotated[User, Depends(required_user)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str, Header(min_length=8, max_length=128)],
) -> dict[str, object]:
    response.headers["Cache-Control"] = "private, no-store"
    _write_origin(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", idempotency_key):
        raise HTTPException(422, detail={"code": "INVALID_IDEMPOTENCY_KEY"})
    return create_checkout(
        session, user, idempotency_key, request.app.state.settings, _provider(request)
    )


@router.post("/billing/portal")
def portal(
    request: Request,
    response: Response,
    body: EmptyBody,
    user: Annotated[User, Depends(required_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    response.headers["Cache-Control"] = "private, no-store"
    _write_origin(request)
    try:
        return {"url": create_portal(session, user, _provider(request))}
    except (CreemError, BillingMismatch, KeyError):
        raise HTTPException(503, detail={"code": "BILLING_UNAVAILABLE"}) from None


@router.post("/webhooks/creem")
async def webhook(request: Request, session: Annotated[Session, Depends(get_session)]):
    _provider(request)
    signature = request.headers.get("creem-signature", "")
    if not re.fullmatch(r"[a-f0-9]{64}", signature):
        raise HTTPException(400, detail={"code": "INVALID_SIGNATURE"})
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_WEBHOOK_BYTES:
            raise HTTPException(413, detail={"code": "WEBHOOK_TOO_LARGE"})
    try:
        receive_event(
            session,
            bytes(raw),
            signature,
            request.app.state.settings.creem_webhook_secret.get_secret_value(),
        )
    except (BillingMismatch, json.JSONDecodeError, UnicodeDecodeError, RecursionError, ValueError):
        session.rollback()
        raise HTTPException(400, detail={"code": "INVALID_WEBHOOK"}) from None
    try:
        # Return 200 only after inbox durability.
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(503, detail={"code": "BILLING_STORAGE_UNAVAILABLE"}) from None
    return {"received": True}

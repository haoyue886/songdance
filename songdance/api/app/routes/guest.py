from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import GuestTrial
from app.services.guest_usage import issue_visitor, visitor_id

router = APIRouter(prefix="/guest", tags=["guest"])


@router.post("/session")
def guest_session(
    request: Request, response: Response, session: Annotated[Session, Depends(get_session)]
) -> dict[str, object]:
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "private, no-store"
    if not settings.guest_usage_enabled:
        raise HTTPException(503, detail={"code": "GUEST_USAGE_DISABLED"})
    if request.headers.get("origin") not in settings.cors_origin_list:
        raise HTTPException(403, detail={"code": "ORIGIN_REJECTED"})
    token = request.headers.get("X-Visitor-Token")
    if token is None:
        token = issue_visitor(settings)
    identity = visitor_id(settings, token)
    trial = session.get(GuestTrial, identity)
    return {
        "visitor_token": token,
        "remaining": 0 if trial and (trial.reserved or trial.consumed) else 1,
        "reserved": trial.reserved if trial else 0,
        "used": trial.consumed if trial else 0,
        "max_clip_seconds": 30,
    }

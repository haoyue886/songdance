"""Server-to-server email routes. Feature closed by default; no browser credentials accepted."""

import asyncio

from fastapi import APIRouter, Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.services.mail_contract import (
    MailError,
    event_key,
    message_bytes,
    otp_message,
    verified_payload,
)
from app.services.mail_delivery import MailDeliveryService
from app.services.resend_client import ResendClient

router = APIRouter(tags=["mail"])


async def handle(request: Request, *, resend: bool) -> JSONResponse:
    try:
        settings = request.app.state.settings
        if not settings.mail_enabled:
            raise MailError("MAIL_DISABLED", 503)
        # Entire application wait is bounded below Supabase's 5-second HTTP hook budget.
        async with asyncio.timeout(4):
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > (65536 if resend else 20480):
                    raise MailError("MAIL_BODY_TOO_LARGE", 413)
            prefix = "svix" if resend else "webhook"
            for part in ("id", "timestamp", "signature"):
                if len(request.headers.getlist(f"{prefix}-{part}")) != 1:
                    raise MailError("MAIL_SIGNATURE_INVALID", 401)
            secret = (
                settings.resend_webhook_secret if resend else settings.supabase_email_hook_secret
            )
            event_id, payload = verified_payload(
                bytes(body), dict(request.headers), secret.get_secret_value(), resend=resend,
            )
            service = MailDeliveryService(settings, request.app.state.session_factory)
            if resend:
                await run_in_threadpool(service.receive_event, event_id, bytes(body), payload)
            else:
                delivery_id = event_key(settings, "supabase", event_id)
                message, action = otp_message(settings, payload, delivery_id)
                encoded = message_bytes(message)
                attempt = await run_in_threadpool(
                    service.claim, delivery_id, bytes(body), encoded, message["to"][0], action,
                )
                if attempt:
                    client = getattr(request.app.state, "mail_client", None) or ResendClient(
                        settings.resend_api_key.get_secret_value(),
                    )
                    result = await client.send(encoded, "songdance-otp/" + delivery_id)
                    await run_in_threadpool(service.finish, delivery_id, attempt, result)
                    if result.status != "accepted":
                        raise MailError(
                            "MAIL_DELIVERY_UNAVAILABLE",
                            400 if result.status == "rejected" else 503,
                            None if result.status == "rejected" else result.retry_after,
                        )
        return JSONResponse({}, headers={"Cache-Control": "no-store"})
    except (SQLAlchemyError, TimeoutError):
        error = MailError("MAIL_TEMPORARILY_UNAVAILABLE", 503, 2)
    except MailError as failure:
        error = failure
    headers = {"Cache-Control": "no-store"}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
    # Fixed safe errors in the documented Supabase hook response shape.
    return JSONResponse({"error": {"http_code": error.status, "message": error.code}},
                        status_code=error.status, headers=headers)


@router.post("/webhooks/supabase/email")
async def supabase_email(request: Request) -> JSONResponse:
    return await handle(request, resend=False)


@router.post("/webhooks/resend")
async def resend_event(request: Request) -> JSONResponse:
    return await handle(request, resend=True)

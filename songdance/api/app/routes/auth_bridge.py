import ipaddress
import json
import re
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.services.auth import auth_error
from app.services.auth_coordination import AuthCoordinator

router = APIRouter(prefix="/auth/bridge", tags=["server-auth"])
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")


@router.post("/{action}")
async def bridge(action: str, request: Request) -> JSONResponse:
    settings = request.app.state.settings
    supplied = request.headers.get("x-auth-bridge", "")
    if not settings.auth_enabled or not secrets.compare_digest(
        supplied.encode(), settings.auth_bridge_secret.get_secret_value().encode()
    ):
        raise auth_error(404, "AUTH_UNAVAILABLE")
    if action not in {"otp-start", "otp-attempt", "otp-consume", "refresh"}:
        raise auth_error(404)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 8192:
            raise auth_error(413)
    try:
        payload = json.loads(data)
        if not isinstance(payload, dict):
            raise ValueError()
        coordinator: AuthCoordinator = request.app.state.auth_coordinator
        if action == "refresh":
            token = payload.get("refresh_token")
            if not isinstance(token, str) or not 1 <= len(token) <= 4096:
                raise ValueError()
            result = await run_in_threadpool(coordinator.refresh, token)
        else:
            email = payload.get("email", "")
            if not isinstance(email, str) or len(email) > 254 or not EMAIL.fullmatch(email):
                raise ValueError()
            email = email.lower()
            if action == "otp-start":
                client = str(ipaddress.ip_address(payload.get("client_ip", "127.0.0.1")))
                result = await run_in_threadpool(coordinator.start_otp, email, client)
            else:
                challenge = payload.get("challenge")
                if not isinstance(challenge, str) or not 20 <= len(challenge) <= 128:
                    raise ValueError()
                result = await run_in_threadpool(
                    coordinator.attempt_otp, challenge, email, action == "otp-consume"
                )
    except HTTPException:
        raise
    except (ValueError, TypeError):
        raise auth_error(400) from None
    except Exception:
        raise auth_error(503, "AUTH_UNAVAILABLE") from None
    return JSONResponse(result, headers={"Cache-Control": "private, no-store"})

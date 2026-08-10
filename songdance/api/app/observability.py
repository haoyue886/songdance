import json
import logging
import re
import secrets
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
logger = logging.getLogger("songdance.api")


def configure_logging() -> None:
    logging.getLogger("uvicorn.access").disabled = True
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "event": record.getMessage()}
        fields = getattr(record, "event_fields", {})
        if isinstance(fields, dict):
            payload.update({key: value for key, value in fields.items() if value is not None})
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def log_event(event: str, **fields: object) -> None:
    logger.info(event, extra={"event_fields": fields})


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else secrets.token_hex(16)
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            log_event(
                "http_request",
                request_id=request_id,
                method=request.method,
                route=route_path,
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

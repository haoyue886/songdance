from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginEnforcementMiddleware:
    def __init__(self, app: ASGIApp, *, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method") in UNSAFE_METHODS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            same_origin = self._request_origin(scope, headers)
            if (
                origin is not None
                and origin not in self.allowed_origins
                and origin != same_origin
            ):
                response = JSONResponse(
                    status_code=403,
                    content={"detail": {"code": "ORIGIN_REJECTED", "message": "Origin rejected"}},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _request_origin(scope: Scope, headers: Headers) -> str | None:
        host = headers.get("host")
        if not host:
            return None
        forwarded_proto = headers.get("x-forwarded-proto", "").split(",")[-1].strip()
        scheme = forwarded_proto or str(scope.get("scheme", "http"))
        if scheme not in {"http", "https"}:
            return None
        return f"{scheme}://{host}"

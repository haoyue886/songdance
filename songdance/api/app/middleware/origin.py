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
            origin = Headers(scope=scope).get("origin")
            if origin is not None and origin not in self.allowed_origins:
                response = JSONResponse(
                    status_code=403,
                    content={"detail": {"code": "ORIGIN_REJECTED", "message": "Origin rejected"}},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

from ipaddress import IPv4Network, IPv6Network, ip_address

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class TrustedProxyOnlyMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        networks: list[IPv4Network | IPv6Network],
    ) -> None:
        self.app = app
        self.enabled = enabled
        self.networks = networks

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.enabled and scope["type"] == "http" and not self._trusted(scope):
            response = JSONResponse(
                status_code=403,
                content={"detail": {"code": "UNTRUSTED_PROXY", "message": "Request rejected"}},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _trusted(self, scope: Scope) -> bool:
        client = scope.get("client")
        if client is None:
            return False
        try:
            peer = ip_address(client[0])
        except ValueError:
            return False
        return any(peer in network for network in self.networks)

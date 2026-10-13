"""One bounded attempt; retry scheduling belongs to the durable hook record."""

import asyncio
import json
import re
from dataclasses import dataclass
from uuid import UUID

import httpx


@dataclass(frozen=True)
class SendResult:
    status: str
    message_id: str | None = None
    error_code: str | None = None
    retry_after: int = 2


class ResendClient:
    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key, self.transport = api_key, transport

    async def send(self, body: bytes, key: str) -> SendResult:
        try:
            # Includes connect, reads and trickling responses. No redirects or automatic retries.
            async with asyncio.timeout(3):
                async with httpx.AsyncClient(
                    transport=self.transport, timeout=2, follow_redirects=False, trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST", "https://api.resend.com/emails", content=body,
                        headers={"Authorization": f"Bearer {self.api_key}",
                                 "Content-Type": "application/json", "Idempotency-Key": key},
                    ) as response:
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 32768:
                                return SendResult("unknown", error_code="RESPONSE_INVALID")
                        try:
                            data = json.loads(raw)
                        except (ValueError, RecursionError):
                            data = None
                        if 200 <= response.status_code < 300:
                            try:
                                message_id = str(UUID(data["id"]))
                            except (KeyError, ValueError, TypeError, AttributeError):
                                return SendResult("unknown", error_code="RESPONSE_INVALID")
                            return SendResult("accepted", message_id=message_id)
                        name = data.get("name") if isinstance(data, dict) else None
                        name = name if isinstance(name, str) else None
                        delay = response.headers.get("retry-after", "2")
                        retry_after = (
                            min(600, max(2, int(delay)))
                            if re.fullmatch(r"[0-9]{1,6}", delay) else 60
                        )
                        if response.status_code == 429:
                            if name in {"daily_quota_exceeded", "monthly_quota_exceeded"}:
                                return SendResult("rejected", error_code="PROVIDER_QUOTA")
                            return SendResult("retry", error_code="PROVIDER_RATE_LIMIT",
                                              retry_after=retry_after)
                        if response.status_code == 409 and name == "concurrent_idempotent_requests":
                            return SendResult("retry", error_code="PROVIDER_BUSY")
                        if response.status_code >= 500:
                            return SendResult("unknown", error_code="PROVIDER_UNAVAILABLE",
                                              retry_after=retry_after)
                        return SendResult("rejected", error_code="PROVIDER_REJECTED")
        except (TimeoutError, httpx.HTTPError):
            # A timeout after upload is NOT proof that no email was accepted.
            return SendResult("unknown", error_code="PROVIDER_OUTCOME_UNKNOWN")

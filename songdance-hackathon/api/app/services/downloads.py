import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from app.settings import Settings


@dataclass(frozen=True)
class DownloadTicket:
    path: str
    expires_at: int


def create_download_ticket(job_id: str, file_type: str, settings: Settings) -> DownloadTicket:
    expires_at = int(time.time()) + settings.download_url_ttl_seconds
    signature = _signature(job_id, file_type, expires_at, settings)
    query = urlencode({"expires": expires_at, "signature": signature})
    return DownloadTicket(
        path=f"/jobs/{job_id}/files/{file_type}?{query}",
        expires_at=expires_at,
    )


def verify_download_ticket(
    job_id: str,
    file_type: str,
    expires_at: int,
    signature: str,
    settings: Settings,
) -> bool:
    now = int(time.time())
    if expires_at < now or expires_at > now + settings.download_url_ttl_seconds + 30:
        return False
    expected = _signature(job_id, file_type, expires_at, settings)
    return hmac.compare_digest(signature, expected)


def _signature(job_id: str, file_type: str, expires_at: int, settings: Settings) -> str:
    payload = f"{job_id}:{file_type}:{expires_at}".encode()
    secret = settings.download_signing_secret.get_secret_value().encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()

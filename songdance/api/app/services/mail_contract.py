"""Strict, test-only email contract. Never expose provider payloads in errors."""

import base64
import hashlib
import hmac
import json
import re
from html import escape
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import UUID

from standardwebhooks import Webhook, WebhookVerificationError

if TYPE_CHECKING:
    from app.settings import Settings


class MailError(Exception):
    def __init__(self, code: str, status: int = 400, retry_after: int | None = None):
        super().__init__(code)
        self.code, self.status, self.retry_after = code, status, retry_after


def address(value: object) -> str:
    if not isinstance(value, str) or len(value) > 254 or not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value,
    ):
        raise MailError("MAIL_ADDRESS_INVALID")
    return value.lower()


def hook_secret(value: str) -> str:
    # Supabase wraps the Standard Webhooks secret in a version prefix.
    secret = value.removeprefix("v1,")
    if not secret.startswith("whsec_"):
        raise ValueError("Mail hook secret must use whsec format")
    try:
        encoded = secret[6:]
        decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
    except ValueError:
        raise ValueError("Invalid mail hook secret") from None
    # Svix's official verification example uses a 24-byte key (32 base64 characters).
    if len(decoded) < 24:
        raise ValueError("Mail hook secret must contain at least 24 bytes")
    return "whsec_" + base64.b64encode(decoded).decode()


def validate_mail_settings(settings: "Settings") -> None:
    if settings.environment == "production":
        raise ValueError("Mail integration is test-only until delivery acceptance")
    if not re.fullmatch(r"[a-z0-9]{20}", settings.mail_project_ref) or (
        settings.supabase_url.rstrip("/")
        != f"https://{settings.mail_project_ref}.supabase.co"
    ):
        raise ValueError("Mail must bind to the configured Supabase project")
    site = urlsplit(settings.mail_site_url)
    if (
        settings.mail_site_url not in settings.cors_origin_list
        or site.path or site.query or site.fragment or site.username or site.password
        or not (site.scheme == "https" or (
            site.scheme == "http" and site.hostname in {"localhost", "127.0.0.1", "::1"}
        ))
    ):
        raise ValueError("Mail site must be an exact configured site origin")
    if settings.mail_from != "auth@mail.notavue.io":
        raise ValueError("Mail sender must be the verified authentication identity")
    if not settings.support_email or not settings.mail_support_verified:
        raise ValueError("Mail requires tested support receiving and reply configuration")
    try:
        address(settings.support_email)
        recipients = settings.mail_test_recipients.split(",")
        if not 1 <= len(recipients) <= 10:
            raise MailError("MAIL_TEST_RECIPIENTS_INVALID")
        for recipient in recipients:
            address(recipient.strip())
    except MailError:
        raise ValueError("Mail requires valid support and explicit test recipients") from None
    key = settings.resend_api_key.get_secret_value()
    if not re.fullmatch(r"re_[A-Za-z0-9_-]{10,200}", key):
        raise ValueError("Mail requires a Resend sending key")
    secrets = [
        hook_secret(settings.supabase_email_hook_secret.get_secret_value()),
        hook_secret(settings.resend_webhook_secret.get_secret_value()),
        settings.mail_digest_secret.get_secret_value(),
    ]
    if len(secrets[2]) < 32 or len(set(secrets)) != 3:
        raise ValueError("Mail secrets must be independent with a 32+ character digest key")


def digest(settings: "Settings", purpose: str, data: bytes) -> str:
    return hmac.new(
        settings.mail_digest_secret.get_secret_value().encode(),
        purpose.encode() + b"\0" + data, hashlib.sha256,
    ).hexdigest()


def event_key(settings: "Settings", provider: str, event_id: str) -> str:
    return hashlib.sha256(f"{settings.mail_project_ref}/{provider}/{event_id}".encode()).hexdigest()


def verified_payload(raw: bytes, headers: dict[str, str], secret: str, *, resend: bool):
    prefix = "svix" if resend else "webhook"
    # Reject ambiguous duplicate headers in the route before calling this adapter.
    selected = {f"webhook-{part}": headers.get(f"{prefix}-{part}", "")
                for part in ("id", "timestamp", "signature")}
    event_id = selected["webhook-id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_id):
        raise MailError("MAIL_SIGNATURE_INVALID", 401)
    if any(len(value) > 4096 for value in selected.values()):
        raise MailError("MAIL_SIGNATURE_INVALID", 401)
    try:
        # Svix and Standard Webhooks share the signature scheme; only header names differ.
        payload = Webhook(hook_secret(secret)).verify(raw, selected)
    except (WebhookVerificationError, ValueError, TypeError, OverflowError, RecursionError):
        raise MailError("MAIL_SIGNATURE_INVALID", 401) from None
    if not isinstance(payload, dict):
        raise MailError("MAIL_PAYLOAD_INVALID")
    return event_id, payload


def otp_message(settings: "Settings", payload: dict, delivery_id: str) -> tuple[dict, str]:
    user, data = payload.get("user"), payload.get("email_data")
    if not isinstance(user, dict) or not isinstance(data, dict):
        raise MailError("MAIL_PAYLOAD_INVALID")
    try:
        UUID(user.get("id", ""))
    except (ValueError, TypeError, AttributeError):
        raise MailError("MAIL_PAYLOAD_INVALID") from None
    recipient = address(user.get("email"))
    if recipient not in {address(v.strip()) for v in settings.mail_test_recipients.split(",")}:
        raise MailError("MAIL_RECIPIENT_NOT_ALLOWED")
    # Supabase Auth sends API.ExternalURL here, not the application's Site URL.
    # Pin the project origin and its auth mount; never use this field for template links.
    provider_origin = settings.supabase_url.rstrip("/")
    if data.get("site_url") not in (provider_origin, provider_origin + "/auth/v1"):
        raise MailError("MAIL_PROVIDER_URL_MISMATCH")
    action = data.get("email_action_type")
    if not isinstance(action, str) or action not in {"signup", "magiclink", "reauthentication"}:
        # The hook replaces ALL Supabase email. Unsupported types must never be acknowledged.
        raise MailError("MAIL_ACTION_UNSUPPORTED")
    token = data.get("token")
    if not isinstance(token, str) or not re.fullmatch(r"(?:[0-9]{6}|[0-9]{8})", token):
        raise MailError("MAIL_OTP_INVALID")
    # All URLs and wording are server-owned. redirect_to, metadata and token_hash are ignored.
    links = [("Privacy", "/privacy"), ("Refund policy", "/refund"), ("Contact", "/contact")]
    text = (
        f"Your Notavue verification code is {token}.\n"
        "It expires 10 minutes after your request. Do not share this code.\n"
        "If you did not request this code, you can ignore this email.\n"
        + "\n".join(f"{label}: {settings.mail_site_url}{path}" for label, path in links)
        + f"\nSupport: {settings.support_email}\n"
    )
    html = (
        "<h1>Notavue verification code</h1>"
        f"<p style=\"font-size:28px;letter-spacing:4px\">{token}</p>"
        "<p>It expires 10 minutes after your request. Do not share this code.</p>"
        "<p>If you did not request this code, you can ignore this email.</p><p>"
        + " | ".join(f'<a href="{escape(settings.mail_site_url + path)}">{label}</a>'
                     for label, path in links)
        + f'</p><p>Support: {escape(settings.support_email)}</p>'
    )
    return {
        "from": settings.mail_from, "to": [recipient],
        "reply_to": settings.support_email, "subject": "Your Notavue verification code",
        "text": text, "html": html,
        "tags": [{"name": "songdance_delivery", "value": delivery_id}],
    }, action


def message_bytes(message: dict) -> bytes:
    return json.dumps(message, sort_keys=True, separators=(",", ":")).encode()

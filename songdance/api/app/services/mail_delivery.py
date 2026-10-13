"""Durable claims survive restart; retries require the same signed Supabase payload."""

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models.mail import MailDelivery, MailEvent, MailSuppression
from app.services.mail_contract import MailError, address, digest, event_key
from app.services.resend_client import SendResult

MAX_ATTEMPTS = 3
RETRY_WINDOW_SECONDS = 120  # Strictly shorter than OTP lifetime and Resend's 24h key retention.
LEASE_SECONDS = 4


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class MailDeliveryService:
    def __init__(self, settings, session_factory):
        self.settings, self.sessions = settings, session_factory

    def claim(self, delivery_id: str, raw: bytes, body: bytes, recipient: str, action: str) -> int:
        """Return the fencing attempt number; zero means already durably accepted."""
        now = datetime.now(UTC)
        request_hash = digest(self.settings, "request", raw)
        message_hash = digest(self.settings, "message", body)
        recipient_hash = digest(self.settings, "recipient", recipient.encode())
        with self.sessions() as session:
            if session.get(MailDelivery, delivery_id) is None:
                session.add(MailDelivery(
                    id=delivery_id, request_digest=request_hash, message_digest=message_hash,
                    recipient_digest=recipient_hash, action=action,
                    next_attempt_at=now, expires_at=now + timedelta(seconds=RETRY_WINDOW_SECONDS),
                ))
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()  # Concurrent first delivery: use the winner's tombstone.
            row = session.get(MailDelivery, delivery_id)
            if row is None:
                raise MailError("MAIL_STORAGE_UNAVAILABLE", 503, 2)
            if row.request_digest != request_hash or row.message_digest != message_hash:
                raise MailError("MAIL_IDEMPOTENCY_CONFLICT", 409)
            if row.status == "accepted":
                return 0
            if session.get(MailSuppression, recipient_hash) is not None:
                raise MailError("MAIL_RECIPIENT_SUPPRESSED")
            if row.status == "rejected":
                raise MailError("MAIL_DELIVERY_REJECTED")
            if now >= utc(row.expires_at) or row.attempts >= MAX_ATTEMPTS:
                raise MailError("MAIL_RETRY_EXHAUSTED")
            if now < utc(row.next_attempt_at):
                delay = max(1, math.ceil((utc(row.next_attempt_at) - now).total_seconds()))
                raise MailError("MAIL_RETRY_LATER", 503, delay)
            attempt = row.attempts + 1
            changed = session.execute(update(MailDelivery).execution_options(
                synchronize_session=False,
            ).where(
                MailDelivery.id == delivery_id, MailDelivery.attempts == row.attempts,
                MailDelivery.status == row.status, MailDelivery.next_attempt_at <= now,
            ).values(status="sending", attempts=attempt,
                     next_attempt_at=now + timedelta(seconds=LEASE_SECONDS)))
            session.commit()
            if changed.rowcount != 1:
                raise MailError("MAIL_RETRY_LATER", 503, 2)
            return attempt

    def finish(self, delivery_id: str, attempt: int, result: SendResult) -> None:
        with self.sessions() as session:
            changed = session.execute(update(MailDelivery).where(
                MailDelivery.id == delivery_id, MailDelivery.attempts == attempt,
                MailDelivery.status == "sending",
            ).values(status=result.status, provider_id=result.message_id,
                     error_code=result.error_code,
                     next_attempt_at=datetime.now(UTC) + timedelta(seconds=result.retry_after)))
            session.commit()
            if changed.rowcount != 1:
                raise MailError("MAIL_ATTEMPT_SUPERSEDED", 503, 2)

    def receive_event(self, event_id: str, raw: bytes, payload: dict) -> None:
        kind, data = payload.get("type"), payload.get("data")
        if not isinstance(kind, str) or not kind.startswith("email.") or len(kind) > 64:
            raise MailError("MAIL_EVENT_INVALID")
        if not isinstance(data, dict):
            raise MailError("MAIL_EVENT_INVALID")
        try:
            provider_id = str(UUID(data.get("email_id", "")))
        except (ValueError, TypeError, AttributeError):
            raise MailError("MAIL_EVENT_INVALID") from None
        key = event_key(self.settings, "resend", event_id)
        body_hash = digest(self.settings, "event", raw)
        # Retry only database uniqueness races; never invoke the sender from event processing.
        for _ in range(3):
            try:
                with self.sessions() as session:
                    prior = session.get(MailEvent, key)
                    if prior:
                        if prior.body_digest != body_hash:
                            raise MailError("MAIL_EVENT_CONFLICT", 409)
                        return
                    tags = data.get("tags")
                    delivery_id = tags.get("songdance_delivery") if isinstance(tags, dict) else None
                    row = session.get(MailDelivery, delivery_id) if (
                        isinstance(delivery_id, str) and len(delivery_id) == 64
                    ) else None
                    outcome = "ignored"
                    if row is not None and data.get("from") == self.settings.mail_from:
                        recipients = data.get("to")
                        if not isinstance(recipients, list) or len(recipients) != 1:
                            raise MailError("MAIL_EVENT_INVALID")
                        recipient_hash = digest(
                            self.settings, "recipient", address(recipients[0]).encode(),
                        )
                        if recipient_hash != row.recipient_digest or (
                            row.provider_id is not None and row.provider_id != provider_id
                        ):
                            raise MailError("MAIL_EVENT_MISMATCH")
                        reason = kind if kind in {"email.complained", "email.suppressed"} else None
                        if kind == "email.bounced":
                            bounce = data.get("bounce")
                            if not isinstance(bounce, dict) or not isinstance(
                                bounce.get("type"), str,
                            ) or bounce["type"] not in {
                                "Permanent", "Temporary", "Transient", "Undetermined",
                            }:
                                raise MailError("MAIL_EVENT_INVALID")
                            if bounce["type"] == "Permanent":
                                reason = "email.bounced"
                        if reason and session.get(MailSuppression, recipient_hash) is None:
                            session.add(MailSuppression(
                                id=recipient_hash, reason=reason, event_id=key,
                            ))
                        # No delivered/opened/etc event can clear or weaken a suppression.
                        outcome = "suppressed" if reason else "recorded"
                    session.add(MailEvent(id=key, body_digest=body_hash, event_type=kind,
                                          provider_id=provider_id, outcome=outcome))
                    session.commit()  # Event and suppression are atomic; only then acknowledge.
                return
            except IntegrityError:
                continue
        raise MailError("MAIL_STORAGE_UNAVAILABLE", 503, 2)

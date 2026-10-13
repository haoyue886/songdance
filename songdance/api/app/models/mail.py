"""Minimal email audit data. No OTP, address, token hash, body or auth identity."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MailDelivery(TimestampMixin, Base):
    __tablename__ = "mail_deliveries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    message_digest: Mapped[str] = mapped_column(String(64))
    recipient_digest: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    error_code: Mapped[str | None] = mapped_column(String(64))


class MailEvent(TimestampMixin, Base):
    __tablename__ = "mail_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    body_digest: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    provider_id: Mapped[str] = mapped_column(String(36))
    outcome: Mapped[str] = mapped_column(String(24))


class MailSuppression(TimestampMixin, Base):
    __tablename__ = "mail_suppressions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason: Mapped[str] = mapped_column(String(64))
    event_id: Mapped[str] = mapped_column(String(64))

"""Durable payment identity, checkout intents, and signed-event inbox."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BillingAccount(TimestampMixin, Base):
    __tablename__ = "billing_accounts"
    __table_args__ = (
        UniqueConstraint("environment", "user_id", name="uq_billing_account_owner"),
        UniqueConstraint("environment", "customer_id", name="uq_billing_customer"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    environment: Mapped[str] = mapped_column(String(8))
    customer_id: Mapped[str | None] = mapped_column(String(255))
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CheckoutSession(TimestampMixin, Base):
    __tablename__ = "checkout_sessions"
    __table_args__ = (
        UniqueConstraint("environment", "user_id", "idempotency_key", name="uq_checkout_key"),
        UniqueConstraint("environment", "provider_id", name="uq_checkout_provider"),
        Index(
            "uq_checkout_open",
            "environment",
            "user_id",
            unique=True,
            sqlite_where=text("status IN ('creating', 'pending', 'uncertain')"),
            postgresql_where=text("status IN ('creating', 'pending', 'uncertain')"),
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    environment: Mapped[str] = mapped_column(String(8))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    provider_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="creating")
    checkout_url: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[str] = mapped_column(String(255))
    plan_version: Mapped[str] = mapped_column(String(64))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    limit_seconds: Mapped[int] = mapped_column(Integer)
    max_clip_seconds: Mapped[int] = mapped_column(Integer)
    success_url: Mapped[str] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))


class BillingSubscription(TimestampMixin, Base):
    __tablename__ = "billing_subscriptions"
    __table_args__ = (UniqueConstraint("environment", "provider_id", name="uq_billing_sub"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    environment: Mapped[str] = mapped_column(String(8))
    provider_id: Mapped[str] = mapped_column(String(255))
    customer_id: Mapped[str] = mapped_column(String(255))
    checkout_id: Mapped[str] = mapped_column(
        ForeignKey("checkout_sessions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(32))
    provider_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BillingWebhookEvent(TimestampMixin, Base):
    __tablename__ = "billing_webhook_events"
    __table_args__ = (UniqueConstraint("environment", "event_id", name="uq_billing_event"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment: Mapped[str] = mapped_column(String(8))
    event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(64))
    body_hash: Mapped[str] = mapped_column(String(64))
    # Minimized references, not the customer's email/address or complete provider payload.
    references: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64))

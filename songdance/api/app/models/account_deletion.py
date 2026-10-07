from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AccountDeletion(TimestampMixin, Base):
    __tablename__ = "account_deletions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    phase: Mapped[str] = mapped_column(String(24), default="billing")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_failures: Mapped[int] = mapped_column(Integer, default=0)
    auth_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))


class AccountDeletionSubscription(TimestampMixin, Base):
    __tablename__ = "account_deletion_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "deletion_id", "environment", "subscription_id", name="uq_account_deletion_subscription"
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    deletion_id: Mapped[str] = mapped_column(
        ForeignKey("account_deletions.id", ondelete="RESTRICT"), index=True
    )
    environment: Mapped[str] = mapped_column(String(8))
    subscription_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

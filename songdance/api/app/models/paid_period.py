from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PaidPeriod(TimestampMixin, Base):
    __tablename__ = "paid_periods"
    __table_args__ = (
        UniqueConstraint("environment", "transaction_id", name="uq_paid_transaction"),
        UniqueConstraint(
            "environment",
            "subscription_id",
            "period_start",
            "period_end",
            name="uq_paid_subscription_period",
        ),
        UniqueConstraint("usage_period_id", name="uq_paid_usage_period"),
        CheckConstraint("environment IN ('test', 'live')", name="ck_paid_environment"),
        CheckConstraint("status IN ('active', 'revoked', 'frozen')", name="ck_paid_status"),
        CheckConstraint("period_end > period_start", name="ck_paid_period_order"),
        CheckConstraint("amount_minor > 0", name="ck_paid_amount_positive"),
        CheckConstraint("max_clip_seconds > 0 AND max_clip_seconds <= 90", name="ck_paid_clip"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    environment: Mapped[str] = mapped_column(String(8), nullable=False)
    transaction_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_version: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_clip_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    usage_period_id: Mapped[str] = mapped_column(
        ForeignKey("usage_periods.id", ondelete="RESTRICT"), nullable=False
    )

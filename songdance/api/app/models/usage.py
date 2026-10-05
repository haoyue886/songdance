from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UsagePeriod(TimestampMixin, Base):
    __tablename__ = "usage_periods"
    __table_args__ = (
        UniqueConstraint("user_id", "entitlement_type", "period_key", name="uq_usage_period"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    entitlement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    period_key: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    limit_units: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UsageLedger(TimestampMixin, Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (
        UniqueConstraint("reservation_id", "event_type", name="uq_usage_terminal_event"),
        Index(
            "uq_usage_single_terminal",
            "reservation_id",
            unique=True,
            sqlite_where=text("event_type IN ('consume', 'release')"),
            postgresql_where=text("event_type IN ('consume', 'release')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    period_id: Mapped[str] = mapped_column(
        ForeignKey("usage_periods.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    reservation_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}")

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GuestTrial(TimestampMixin, Base):
    __tablename__ = "guest_trials"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GuestDay(TimestampMixin, Base):
    """One durable new-task admission per hashed IP and UTC date; no raw IP."""

    __tablename__ = "guest_days"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    job_id: Mapped[str] = mapped_column(String(64))


class GuestSubmission(TimestampMixin, Base):
    __tablename__ = "guest_submissions"
    __table_args__ = (UniqueConstraint("trial_id", "submission_key", name="uq_guest_submission"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trial_id: Mapped[str] = mapped_column(
        ForeignKey("guest_trials.id", ondelete="RESTRICT"), index=True
    )
    submission_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(16))


class GuestLedger(TimestampMixin, Base):
    __tablename__ = "guest_ledger"
    __table_args__ = (
        UniqueConstraint("reservation_id", "event_type", name="uq_guest_event"),
        Index(
            "uq_guest_terminal",
            "reservation_id",
            unique=True,
            sqlite_where=text("event_type IN ('consume', 'release')"),
            postgresql_where=text("event_type IN ('consume', 'release')"),
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trial_id: Mapped[str] = mapped_column(
        ForeignKey("guest_trials.id", ondelete="RESTRICT"), index=True
    )
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    reservation_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="{}")

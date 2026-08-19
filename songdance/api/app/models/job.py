from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobStage(StrEnum):
    UPLOAD = "upload"
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    TRANSCRIBING = "transcribing"
    SCORE = "score"
    COMPLETED = "completed"


class TranscriptionJob(TimestampMixin, Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default=JobStatus.QUEUED, nullable=False)
    stage: Mapped[str] = mapped_column(String(24), default=JobStage.QUEUED, nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), default="upload", nullable=False)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    source_asset: Mapped["SourceAsset"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    result: Mapped["TranscriptionResult | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    quality_report: Mapped["TranscriptionQualityReport | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class SourceAsset(TimestampMixin, Base):
    __tablename__ = "source_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("transcription_jobs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))

    job: Mapped[TranscriptionJob] = relationship(back_populates="source_asset")


class TranscriptionResult(TimestampMixin, Base):
    __tablename__ = "transcription_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("transcription_jobs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    tempo: Mapped[float | None] = mapped_column(Float)
    time_signature: Mapped[str | None] = mapped_column(String(16))
    note_count: Mapped[int | None] = mapped_column(Integer)
    quality_flags: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(128))

    job: Mapped[TranscriptionJob] = relationship(back_populates="result")


class TranscriptionQualityReport(TimestampMixin, Base):
    __tablename__ = "transcription_quality_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("transcription_jobs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    report_version: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    job: Mapped[TranscriptionJob] = relationship(back_populates="quality_report")


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("transcription_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="succeeded")
    storage_key: Mapped[str | None] = mapped_column(String(512), unique=True)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))

    job: Mapped[TranscriptionJob] = relationship(back_populates="artifacts")


class AnalyticsEvent(TimestampMixin, Base):
    __tablename__ = "analytics_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    job_id_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    properties: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

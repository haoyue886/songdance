"""Create transcription job tables.

Revision ID: 001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "transcription_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *timestamp_columns(),
    )
    op.create_index("ix_transcription_jobs_expires_at", "transcription_jobs", ["expires_at"])
    op.create_table(
        "source_assets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=64),
            sa.ForeignKey("transcription_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("storage_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        *timestamp_columns(),
    )
    op.create_table(
        "transcription_results",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=64),
            sa.ForeignKey("transcription_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("tempo", sa.Float()),
        sa.Column("time_signature", sa.String(length=16)),
        sa.Column("note_count", sa.Integer()),
        sa.Column("quality_flags", sa.Text()),
        sa.Column("model_version", sa.String(length=128)),
        *timestamp_columns(),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=64),
            sa.ForeignKey("transcription_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        *timestamp_columns(),
    )
    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_job_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_table("transcription_results")
    op.drop_table("source_assets")
    op.drop_index("ix_transcription_jobs_expires_at", table_name="transcription_jobs")
    op.drop_table("transcription_jobs")

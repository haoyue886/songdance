"""Durable submission identity and transactional job dispatch records."""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.add_column(
        "transcription_jobs",
        sa.Column("dispatch_managed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Deliberately omit job FKs: tombstones must survive task/media expiration.
    op.create_table(
        "job_submissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("submission_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "submission_key", name="uq_job_submission"),
    )
    op.create_index("ix_job_submissions_user_id", "job_submissions", ["user_id"])
    op.create_index("ix_job_submissions_job_id", "job_submissions", ["job_id"])
    op.create_table(
        "job_dispatches",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("job_id", "attempt", name="uq_job_dispatch_attempt"),
    )
    op.create_index("ix_job_dispatches_job_id", "job_dispatches", ["job_id"])
    op.create_index("ix_job_dispatches_status", "job_dispatches", ["status"])
    op.create_index("ix_job_dispatches_next_attempt_at", "job_dispatches", ["next_attempt_at"])


def downgrade() -> None:
    connection = op.get_bind()
    # Guard all history before any DDL, including managed tasks without dispatch rows.
    has_history = any(
        connection.scalar(sa.text(f"SELECT count(*) FROM {table}"))
        for table in ("job_submissions", "job_dispatches")
    )
    jobs = sa.table("transcription_jobs", sa.column("dispatch_managed", sa.Boolean()))
    has_managed_jobs = connection.scalar(
        sa.select(sa.func.count()).select_from(jobs).where(jobs.c.dispatch_managed.is_(True))
    )
    if has_history or has_managed_jobs:
        raise RuntimeError(
            "Cannot remove submission or dispatch history or managed tasks; "
            "keep schema and disable new admissions"
        )
    op.drop_table("job_dispatches")
    op.drop_table("job_submissions")
    op.drop_column("transcription_jobs", "dispatch_managed")

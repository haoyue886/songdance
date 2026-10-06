"""Durable anonymous trial admissions, reservations, and settlement history."""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def _trial() -> sa.Column:
    return sa.Column(
        "trial_id", sa.String(64), sa.ForeignKey("guest_trials.id", ondelete="RESTRICT"),
        nullable=False,
    )


def upgrade() -> None:
    # Nullable identifiers preserve every pre-trial job without inventing usage history.
    for column in ("guest_trial_id", "guest_reservation_id"):
        op.add_column("transcription_jobs", sa.Column(column, sa.String(64), nullable=True))
        op.create_index(f"ix_transcription_jobs_{column}", "transcription_jobs", [column])
    op.create_table(
        "guest_trials",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("reserved", sa.Integer(), nullable=False),
        sa.Column("consumed", sa.Integer(), nullable=False),
        *_timestamps(),
    )
    # No job FKs: admission tombstones and settlement history survive task expiration.
    op.create_table(
        "guest_days",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_guest_days_day", "guest_days", ["day"])
    op.create_table(
        "guest_submissions",
        sa.Column("id", sa.String(64), primary_key=True),
        _trial(),
        sa.Column("submission_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("trial_id", "submission_key", name="uq_guest_submission"),
    )
    op.create_index("ix_guest_submissions_trial_id", "guest_submissions", ["trial_id"])
    op.create_index("ix_guest_submissions_job_id", "guest_submissions", ["job_id"])
    op.create_table(
        "guest_ledger",
        sa.Column("id", sa.String(64), primary_key=True),
        _trial(),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("reservation_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("reservation_id", "event_type", name="uq_guest_event"),
    )
    for column in ("trial_id", "job_id", "reservation_id"):
        op.create_index(f"ix_guest_ledger_{column}", "guest_ledger", [column])
    op.create_index(
        "uq_guest_terminal", "guest_ledger", ["reservation_id"], unique=True,
        sqlite_where=sa.text("event_type IN ('consume', 'release')"),
        postgresql_where=sa.text("event_type IN ('consume', 'release')"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    tables = ("guest_ledger", "guest_submissions", "guest_days", "guest_trials")
    # Check all durable records and job identifiers before performing any DDL.
    has_history = any(
        connection.scalar(sa.text(f"SELECT count(*) FROM {table}")) for table in tables
    )
    has_guest_jobs = connection.scalar(sa.text(
        "SELECT count(*) FROM transcription_jobs "
        "WHERE guest_trial_id IS NOT NULL OR guest_reservation_id IS NOT NULL"
    ))
    if has_history or has_guest_jobs:
        raise RuntimeError(
            "Cannot remove guest trial history or guest tasks; "
            "keep schema and disable new admissions"
        )
    for table in tables:
        op.drop_table(table)
    for column in ("guest_reservation_id", "guest_trial_id"):
        op.drop_index(f"ix_transcription_jobs_{column}", table_name="transcription_jobs")
        op.drop_column("transcription_jobs", column)

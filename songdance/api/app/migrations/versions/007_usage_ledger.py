"""Usage periods and immutable reservation/terminal events.

Revision ID: 007
Revises: 006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "usage_periods",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("entitlement_type", sa.String(32), nullable=False),
        sa.Column("period_key", sa.String(64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_units", sa.Integer(), nullable=False),
        sa.Column("reserved_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_units", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "entitlement_type", "period_key", name="uq_usage_period"),
        *_timestamps(),
    )
    op.create_index("ix_usage_periods_user_id", "usage_periods", ["user_id"])
    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "period_id",
            sa.String(64),
            sa.ForeignKey("usage_periods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("reservation_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("reservation_id", "event_type", name="uq_usage_terminal_event"),
        *_timestamps(),
    )
    op.create_index("ix_usage_ledger_period_id", "usage_ledger", ["period_id"])
    op.create_index("ix_usage_ledger_user_id", "usage_ledger", ["user_id"])
    op.create_index("ix_usage_ledger_job_id", "usage_ledger", ["job_id"])
    op.create_index("ix_usage_ledger_reservation_id", "usage_ledger", ["reservation_id"])
    with op.batch_alter_table("transcription_jobs") as batch:
        batch.add_column(sa.Column("usage_reservation_id", sa.String(64)))
        batch.create_index("ix_transcription_jobs_usage_reservation_id", ["usage_reservation_id"])


def downgrade() -> None:
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM usage_ledger"))
    if count:
        raise RuntimeError(
            "Cannot downgrade with usage ledger rows; retain immutable billing history"
        )
    with op.batch_alter_table("transcription_jobs") as batch:
        batch.drop_index("ix_transcription_jobs_usage_reservation_id")
        batch.drop_column("usage_reservation_id")
    op.drop_index("ix_usage_ledger_reservation_id", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_job_id", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_user_id", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_period_id", table_name="usage_ledger")
    op.drop_table("usage_ledger")
    op.drop_index("ix_usage_periods_user_id", table_name="usage_periods")
    op.drop_table("usage_periods")

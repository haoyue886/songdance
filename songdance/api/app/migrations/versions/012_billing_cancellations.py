"""Durable recovery of subscription cancellation after verified refunds."""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_cancellations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column(
            "paid_period_id", sa.String(64),
            sa.ForeignKey("paid_periods.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("subscription_id", sa.String(255), nullable=False),
        sa.Column("transaction_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        *[
            sa.Column(
                name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
            )
            for name in ("created_at", "updated_at")
        ],
        sa.UniqueConstraint("environment", "transaction_id", name="uq_billing_cancellation"),
    )
    for column in ("user_id", "paid_period_id", "status", "next_attempt_at"):
        op.create_index(f"ix_billing_cancellations_{column}", "billing_cancellations", [column])


def downgrade() -> None:
    # Completed and manual-review records are audit history too; check before any DDL.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM billing_cancellations")):
        raise RuntimeError(
            "Cannot remove billing cancellation history; "
            "keep schema and disable new admissions"
        )
    op.drop_table("billing_cancellations")

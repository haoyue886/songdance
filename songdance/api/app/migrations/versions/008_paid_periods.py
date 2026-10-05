"""Paid transaction periods and mutually exclusive usage terminal events."""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    duplicate = op.get_bind().scalar(
        sa.text(
            "SELECT reservation_id FROM usage_ledger WHERE event_type IN ('consume', 'release') "
            "GROUP BY reservation_id HAVING count(*) > 1 LIMIT 1"
        )
    )
    if duplicate is not None:
        raise RuntimeError("Conflicting usage terminal events require audited reconciliation")
    op.create_index(
        "uq_usage_single_terminal",
        "usage_ledger",
        ["reservation_id"],
        unique=True,
        sqlite_where=sa.text("event_type IN ('consume', 'release')"),
        postgresql_where=sa.text("event_type IN ('consume', 'release')"),
    )
    op.create_table(
        "paid_periods",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column("transaction_id", sa.String(255), nullable=False),
        sa.Column("subscription_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.String(255), nullable=False),
        sa.Column("plan_version", sa.String(64), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_clip_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "usage_period_id",
            sa.String(64),
            sa.ForeignKey("usage_periods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("environment", "transaction_id", name="uq_paid_transaction"),
        sa.UniqueConstraint(
            "environment",
            "subscription_id",
            "period_start",
            "period_end",
            name="uq_paid_subscription_period",
        ),
        sa.UniqueConstraint("usage_period_id", name="uq_paid_usage_period"),
        sa.CheckConstraint("environment IN ('test', 'live')", name="ck_paid_environment"),
        sa.CheckConstraint("status IN ('active', 'revoked', 'frozen')", name="ck_paid_status"),
        sa.CheckConstraint("period_end > period_start", name="ck_paid_period_order"),
        sa.CheckConstraint("amount_minor > 0", name="ck_paid_amount_positive"),
        sa.CheckConstraint("max_clip_seconds > 0 AND max_clip_seconds <= 90", name="ck_paid_clip"),
    )
    op.create_index("ix_paid_periods_user_id", "paid_periods", ["user_id"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM paid_periods")):
        raise RuntimeError("Cannot remove paid history; keep schema and disable new admissions")
    op.drop_table("paid_periods")
    op.drop_index("uq_usage_single_terminal", table_name="usage_ledger")

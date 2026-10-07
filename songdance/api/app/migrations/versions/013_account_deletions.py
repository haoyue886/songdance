"""Durable account deletion requests and verified subscription cancellation history."""

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_deletions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False, unique=True,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("retry_failures", sa.Integer(), nullable=False),
        sa.Column("auth_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        *[
            sa.Column(
                name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
            )
            for name in ("created_at", "updated_at")
        ],
    )
    for column in ("status", "next_attempt_at"):
        op.create_index(f"ix_account_deletions_{column}", "account_deletions", [column])
    op.create_table(
        "account_deletion_subscriptions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "deletion_id", sa.String(64),
            sa.ForeignKey("account_deletions.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column("subscription_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        *[
            sa.Column(
                name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
            )
            for name in ("created_at", "updated_at")
        ],
        sa.UniqueConstraint(
            "deletion_id", "environment", "subscription_id",
            name="uq_account_deletion_subscription",
        ),
    )
    op.create_index(
        "ix_account_deletion_subscriptions_deletion_id", "account_deletion_subscriptions",
        ["deletion_id"],
    )


def downgrade() -> None:
    # Every state is audit history; inspect both tables before dropping either one.
    if any(
        op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}"))
        for table in ("account_deletions", "account_deletion_subscriptions")
    ):
        raise RuntimeError(
            "Cannot remove account deletion or subscription cancellation history; "
            "keep schema and disable new admissions"
        )
    op.drop_table("account_deletion_subscriptions")
    op.drop_table("account_deletions")

"""Durable Creem customer identities, checkout intents, and event inbox."""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def _owner() -> sa.Column:
    return sa.Column(
        "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "billing_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        _owner(),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=True),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("environment", "user_id", name="uq_billing_account_owner"),
        sa.UniqueConstraint("environment", "customer_id", name="uq_billing_customer"),
    )
    op.create_index("ix_billing_accounts_user_id", "billing_accounts", ["user_id"])
    op.create_table(
        "checkout_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        _owner(),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("product_id", sa.String(255), nullable=False),
        sa.Column("plan_version", sa.String(64), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("limit_seconds", sa.Integer(), nullable=False),
        sa.Column("max_clip_seconds", sa.Integer(), nullable=False),
        sa.Column("success_url", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("environment", "user_id", "idempotency_key", name="uq_checkout_key"),
        sa.UniqueConstraint("environment", "provider_id", name="uq_checkout_provider"),
    )
    op.create_index("ix_checkout_sessions_user_id", "checkout_sessions", ["user_id"])
    op.create_index(
        "uq_checkout_open", "checkout_sessions", ["environment", "user_id"], unique=True,
        sqlite_where=sa.text("status IN ('creating', 'pending', 'uncertain')"),
        postgresql_where=sa.text("status IN ('creating', 'pending', 'uncertain')"),
    )
    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.String(64), primary_key=True),
        _owner(),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=False),
        sa.Column(
            "checkout_id", sa.String(64),
            sa.ForeignKey("checkout_sessions.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("environment", "provider_id", name="uq_billing_sub"),
    )
    op.create_index("ix_billing_subscriptions_user_id", "billing_subscriptions", ["user_id"])
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("references", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("environment", "event_id", name="uq_billing_event"),
    )
    op.create_index("ix_billing_webhook_events_status", "billing_webhook_events", ["status"])
    op.create_index(
        "ix_billing_webhook_events_next_attempt_at", "billing_webhook_events", ["next_attempt_at"]
    )


def downgrade() -> None:
    tables = (
        "billing_subscriptions", "checkout_sessions", "billing_accounts", "billing_webhook_events"
    )
    # Check every table before any DDL: preserve identities as well as payment audit history.
    for table in tables:
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError(
                "Cannot remove billing identity or audit history; "
                "keep schema and disable new admissions"
            )
    for table in tables:
        op.drop_table(table)

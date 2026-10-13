"""Private email delivery tombstones, signed events and persistent suppressions."""

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "mail_deliveries",
        sa.Column("id", sa.String(64), primary_key=True),
        *[sa.Column(name, sa.String(64), nullable=False)
          for name in ("request_digest", "message_digest", "recipient_digest")],
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_id", sa.String(36), nullable=True, unique=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_mail_deliveries_recipient_digest", "mail_deliveries", ["recipient_digest"])
    op.create_table(
        "mail_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("body_digest", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("provider_id", sa.String(36), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "mail_suppressions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        *timestamps(),
    )


def downgrade() -> None:
    tables = ("mail_suppressions", "mail_events", "mail_deliveries")
    if any(op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}")) for table in tables):
        raise RuntimeError("Cannot remove mail audit/suppression history; disable sending instead")
    for table in tables:
        op.drop_table(table)

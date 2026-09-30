"""Users, provider identities and additive task ownership.

Revision ID: 006
Revises: 005
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(36), nullable=False),
        sa.UniqueConstraint("issuer", "subject", name="uq_auth_issuer_subject"),
        *_timestamps(),
    )
    with op.batch_alter_table("transcription_jobs") as batch:
        batch.add_column(sa.Column("owner_user_id", sa.String(36)))
        batch.add_column(sa.Column("guest_secret_hash", sa.String(64)))
        batch.create_foreign_key(
            "fk_job_owner", "users", ["owner_user_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_index("ix_transcription_jobs_owner_user_id", ["owner_user_id"])


def downgrade() -> None:
    # Do not turn protected tasks into publicly accessible legacy tasks on rollback.
    count = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM transcription_jobs "
            "WHERE owner_user_id IS NOT NULL OR guest_secret_hash IS NOT NULL"
        )
    )
    if count:
        raise RuntimeError("Cannot downgrade while protected tasks exist; retain compatible schema")
    with op.batch_alter_table("transcription_jobs") as batch:
        batch.drop_index("ix_transcription_jobs_owner_user_id")
        batch.drop_constraint("fk_job_owner", type_="foreignkey")
        batch.drop_column("guest_secret_hash")
        batch.drop_column("owner_user_id")
    op.drop_table("auth_identities")
    op.drop_table("users")

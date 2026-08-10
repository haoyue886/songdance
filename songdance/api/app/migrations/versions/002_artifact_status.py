"""Track independent artifact outcomes.

Revision ID: 002
Revises: 001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("artifacts") as batch:
        batch.add_column(
            sa.Column("status", sa.String(length=24), server_default="succeeded", nullable=False)
        )
        batch.add_column(sa.Column("mime_type", sa.String(length=128)))
        batch.add_column(sa.Column("error_code", sa.String(length=64)))
        batch.alter_column("storage_key", existing_type=sa.String(length=512), nullable=True)
        batch.alter_column(
            "size_bytes", existing_type=sa.Integer(), server_default="0", nullable=False
        )


def downgrade() -> None:
    op.execute("DELETE FROM artifacts WHERE storage_key IS NULL")
    with op.batch_alter_table("artifacts") as batch:
        batch.alter_column(
            "size_bytes", existing_type=sa.Integer(), server_default=None, nullable=False
        )
        batch.alter_column("storage_key", existing_type=sa.String(length=512), nullable=False)
        batch.drop_column("error_code")
        batch.drop_column("mime_type")
        batch.drop_column("status")

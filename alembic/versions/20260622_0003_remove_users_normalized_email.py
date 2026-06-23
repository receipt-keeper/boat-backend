"""remove users normalized email

Revision ID: 20260622_0003
Revises: 20260620_0002
Create Date: 2026-06-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260622_0003"
down_revision: str | Sequence[str] | None = "20260620_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "ix_users_normalized_email_unique",
        table_name="users",
        postgresql_where=sa.text("normalized_email IS NOT NULL"),
    )
    op.drop_column("users", "normalized_email")


def downgrade() -> None:
    op.add_column("users", sa.Column("normalized_email", sa.String(length=255), nullable=True))
    op.create_index(
        "ix_users_normalized_email_unique",
        "users",
        ["normalized_email"],
        unique=True,
        postgresql_where=sa.text("normalized_email IS NOT NULL"),
    )

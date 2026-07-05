"""create user push tokens table

Revision ID: 20260704_0012
Revises: 20260702_0011
Create Date: 2026-07-04 00:12:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260704_0012"
down_revision: str | Sequence[str] | None = "20260702_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_push_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fid", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_push_tokens")),
        sa.UniqueConstraint("fid", name=op.f("uq_user_push_tokens_fid")),
    )
    op.create_index(
        op.f("ix_user_push_tokens_user_id"),
        "user_push_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_push_tokens_user_id"), table_name="user_push_tokens")
    op.drop_table("user_push_tokens")

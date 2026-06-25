"""align files schema with ERD

Revision ID: 20260626_0007
Revises: 20260625_0006
Create Date: 2026-06-26 00:07:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260626_0007"
down_revision: str | Sequence[str] | None = "20260625_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("files", "purpose")
    op.drop_column("files", "status")
    op.drop_column("files", "updated_at")
    op.drop_column("file_objects", "storage_backend")
    op.drop_column("file_objects", "updated_at")


def downgrade() -> None:
    op.add_column(
        "file_objects",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "file_objects",
        sa.Column(
            "storage_backend",
            sa.String(length=50),
            server_default="local",
            nullable=False,
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "files",
        sa.Column("status", sa.String(length=50), server_default="available", nullable=False),
    )
    op.add_column(
        "files",
        sa.Column("purpose", sa.String(length=50), server_default="profile_image", nullable=False),
    )

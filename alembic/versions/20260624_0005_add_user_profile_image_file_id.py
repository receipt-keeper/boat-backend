"""add user profile image file id

Revision ID: 20260624_0005
Revises: 20260624_0004
Create Date: 2026-06-24 00:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260624_0005"
down_revision: str | Sequence[str] | None = "20260624_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("profile_image_file_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "profile_image_file_id")

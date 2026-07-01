"""add receipt sub category

Revision ID: 20260701_0010
Revises: 20260628_0009
Create Date: 2026-07-01 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260701_0010"
down_revision: str | Sequence[str] | None = "20260628_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipts",
        sa.Column("sub_category", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receipts", "sub_category")

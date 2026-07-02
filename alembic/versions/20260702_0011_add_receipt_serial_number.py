"""add receipt serial number

Revision ID: 20260702_0011
Revises: 20260701_0011
Create Date: 2026-07-02 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260702_0011"
down_revision: str | Sequence[str] | None = "20260701_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipts",
        sa.Column("serial_number", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receipts", "serial_number")

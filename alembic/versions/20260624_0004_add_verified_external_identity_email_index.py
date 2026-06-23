"""add verified external identity email index

Revision ID: 20260624_0004
Revises: 20260622_0003
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260624_0004"
down_revision: str | Sequence[str] | None = "20260622_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_external_identities_verified_normalized_email",
        "external_identities",
        ["normalized_email"],
        postgresql_where=sa.text("email_verified IS TRUE AND normalized_email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_external_identities_verified_normalized_email",
        table_name="external_identities",
    )

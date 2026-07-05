"""create promotion contents

Revision ID: 20260705_0014
Revises: 20260703_0013
Create Date: 2026-07-05 00:14:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260705_0014"
down_revision: str | Sequence[str] | None = "20260703_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promotion_contents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("banner_image_url", sa.String(length=2048), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["promotion_id"],
            ["promotions.id"],
            name=op.f("fk_promotion_contents_promotion_id_promotions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promotion_contents")),
        sa.UniqueConstraint(
            "promotion_id",
            name=op.f("uq_promotion_contents_promotion_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("promotion_contents")

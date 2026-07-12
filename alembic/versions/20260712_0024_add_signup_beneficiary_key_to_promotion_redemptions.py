"""add signup beneficiary key to promotion redemptions

Revision ID: 20260712_0024
Revises: 20260712_0023
Create Date: 2026-07-12 00:23:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260712_0024"
down_revision: str | Sequence[str] | None = "20260712_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_promotions_context_allowed"),
        "promotions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_promotions_context_allowed"),
        "promotions",
        "context IS NULL OR context IN ('recharge', 'signup')",
    )
    op.add_column(
        "promotion_redemptions",
        sa.Column("beneficiary_key", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "uq_promotion_redemptions_promotion_beneficiary",
        "promotion_redemptions",
        ["promotion_id", "beneficiary_key"],
        unique=True,
        postgresql_where=sa.text("beneficiary_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute("UPDATE promotions SET context = NULL WHERE context = 'signup'")
    op.drop_constraint(
        op.f("ck_promotions_context_allowed"),
        "promotions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_promotions_context_allowed"),
        "promotions",
        "context IS NULL OR context IN ('recharge')",
    )
    op.drop_index(
        "uq_promotion_redemptions_promotion_beneficiary",
        table_name="promotion_redemptions",
    )
    op.drop_column("promotion_redemptions", "beneficiary_key")

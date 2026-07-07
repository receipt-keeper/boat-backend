"""add promotion context

Revision ID: 20260707_0019
Revises: 20260705_0018
Create Date: 2026-07-07 00:19:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260707_0019"
down_revision: str | Sequence[str] | None = "20260705_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("context", sa.String(length=50), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_promotions_context_allowed"),
        "promotions",
        "context IS NULL OR context IN ('recharge')",
    )
    op.create_index(
        "ix_promotions_current_benefit_context",
        "promotions",
        [
            "benefit_feature_key",
            "context",
            "active",
            "expires_at",
            sa.text("starts_at DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "uq_promotions_benefit_context_starts_at",
        "promotions",
        ["benefit_feature_key", "context", "starts_at"],
        unique=True,
        postgresql_where=sa.text("context IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_promotions_benefit_context_starts_at", table_name="promotions")
    op.drop_index("ix_promotions_current_benefit_context", table_name="promotions")
    op.drop_constraint(
        op.f("ck_promotions_context_allowed"),
        "promotions",
        type_="check",
    )
    op.drop_column("promotions", "context")

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260719_0026"
down_revision: str | Sequence[str] | None = "20260717_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REWARDED_AD_PROMOTION_ID = "67a6b0f8-a628-47ae-a2c3-1a5688736829"


def upgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("kind", sa.String(length=50), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_promotions_kind_allowed"),
        "promotions",
        "kind IS NULL OR kind IN ('monthlyAllowance', 'rewardedAd')",
    )
    op.execute(
        sa.text(
            "UPDATE promotions "
            "SET kind = 'monthlyAllowance' "
            "WHERE context = 'recharge' AND benefit_feature_key = 'ocr'"
        )
    )

    op.drop_index("ix_promotions_current_benefit_context", table_name="promotions")
    op.drop_index("uq_promotions_benefit_context_starts_at", table_name="promotions")
    op.create_index(
        "ix_promotions_current_benefit_context_kind",
        "promotions",
        [
            "benefit_feature_key",
            "context",
            "kind",
            "active",
            "expires_at",
            sa.text("starts_at DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "uq_promotions_benefit_context_kind_starts_at",
        "promotions",
        ["benefit_feature_key", "context", "kind", "starts_at"],
        unique=True,
        postgresql_where=sa.text("context IS NOT NULL AND kind IS NOT NULL"),
    )
    op.create_index(
        "uq_promotions_benefit_context_starts_at_without_kind",
        "promotions",
        ["benefit_feature_key", "context", "starts_at"],
        unique=True,
        postgresql_where=sa.text("context IS NOT NULL AND kind IS NULL"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO promotions (
                id,
                name,
                active,
                starts_at,
                expires_at,
                max_redemptions,
                times_redeemed,
                max_redemptions_per_user,
                benefit_feature_key,
                context,
                kind,
                benefit_amount
            )
            VALUES (
                CAST(:promotion_id AS UUID),
                '광고 시청 OCR 크레딧 충전',
                true,
                TIMESTAMPTZ '2026-07-16 15:00:00+00:00',
                NULL,
                NULL,
                0,
                2,
                'ocr',
                'recharge',
                'rewardedAd',
                2
            )
            """
        ).bindparams(promotion_id=REWARDED_AD_PROMOTION_ID)
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM promotions WHERE id = CAST(:promotion_id AS UUID)").bindparams(
            promotion_id=REWARDED_AD_PROMOTION_ID
        )
    )
    op.drop_index(
        "uq_promotions_benefit_context_starts_at_without_kind",
        table_name="promotions",
    )
    op.drop_index(
        "uq_promotions_benefit_context_kind_starts_at",
        table_name="promotions",
    )
    op.drop_index("ix_promotions_current_benefit_context_kind", table_name="promotions")
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
    op.drop_constraint(op.f("ck_promotions_kind_allowed"), "promotions", type_="check")
    op.drop_column("promotions", "kind")

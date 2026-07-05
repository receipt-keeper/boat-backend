"""create promotion tables

Revision ID: 20260705_0016
Revises: 20260705_0015
Create Date: 2026-07-03 00:12:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260705_0016"
down_revision: str | Sequence[str] | None = "20260705_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promotions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("times_redeemed", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "max_redemptions_per_user",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("benefit_feature_key", sa.String(length=50), nullable=False),
        sa.Column("benefit_amount", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "benefit_feature_key IN ('ocr')",
            name=op.f("ck_promotions_benefit_feature_key_allowed"),
        ),
        sa.CheckConstraint(
            "benefit_amount > 0",
            name=op.f("ck_promotions_benefit_amount_positive"),
        ),
        sa.CheckConstraint(
            "max_redemptions IS NULL OR max_redemptions > 0",
            name=op.f("ck_promotions_max_redemptions_positive"),
        ),
        sa.CheckConstraint(
            "times_redeemed >= 0",
            name=op.f("ck_promotions_times_redeemed_non_negative"),
        ),
        sa.CheckConstraint(
            "max_redemptions_per_user > 0",
            name=op.f("ck_promotions_max_redemptions_per_user_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promotions")),
    )
    op.create_table(
        "promotion_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("times_redeemed", sa.Integer(), server_default="0", nullable=False),
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
        sa.CheckConstraint(
            "max_redemptions IS NULL OR max_redemptions > 0",
            name=op.f("ck_promotion_codes_max_redemptions_positive"),
        ),
        sa.CheckConstraint(
            "times_redeemed >= 0",
            name=op.f("ck_promotion_codes_times_redeemed_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["promotion_id"],
            ["promotions.id"],
            name=op.f("fk_promotion_codes_promotion_id_promotions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promotion_codes")),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_promotion_codes_code_unique ON promotion_codes (lower(code))"
        )
    )
    op.create_table(
        "promotion_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("promotion_code_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('granted', 'rejected', 'failed')",
            name=op.f("ck_promotion_redemptions_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["promotion_code_id"],
            ["promotion_codes.id"],
            name=op.f("fk_promotion_redemptions_promotion_code_id_promotion_codes"),
        ),
        sa.ForeignKeyConstraint(
            ["promotion_id"],
            ["promotions.id"],
            name=op.f("fk_promotion_redemptions_promotion_id_promotions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promotion_redemptions")),
        sa.UniqueConstraint(
            "idempotency_key",
            name=op.f("uq_promotion_redemptions_idempotency_key"),
        ),
    )


def downgrade() -> None:
    op.drop_table("promotion_redemptions")
    op.drop_index("ix_promotion_codes_code_unique", table_name="promotion_codes")
    op.drop_table("promotion_codes")
    op.drop_table("promotions")

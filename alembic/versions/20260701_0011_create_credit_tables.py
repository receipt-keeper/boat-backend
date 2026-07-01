"""create credit tables

Revision ID: 20260701_0011
Revises: 20260701_0010
Create Date: 2026-07-01 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260701_0011"
down_revision: str | Sequence[str] | None = "20260701_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_credits",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_key", sa.String(length=50), nullable=False),
        sa.Column(
            "total_granted_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("remaining_count", sa.Integer(), server_default="0", nullable=False),
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
            "feature_key IN ('ocr')",
            name=op.f("ck_user_credits_feature_key_allowed"),
        ),
        sa.CheckConstraint(
            "total_granted_count >= 0",
            name=op.f("ck_user_credits_total_granted_count_non_negative"),
        ),
        sa.CheckConstraint(
            "used_count >= 0",
            name=op.f("ck_user_credits_used_count_non_negative"),
        ),
        sa.CheckConstraint(
            "remaining_count >= 0",
            name=op.f("ck_user_credits_remaining_count_non_negative"),
        ),
        sa.CheckConstraint(
            "total_granted_count = used_count + remaining_count",
            name=op.f("ck_user_credits_counts_consistent"),
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "feature_key",
            name=op.f("pk_user_credits"),
        ),
    )
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_key", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "feature_key IN ('ocr')",
            name=op.f("ck_credit_transactions_feature_key_allowed"),
        ),
        sa.CheckConstraint(
            "reason IN ('monthlyOcrAllowance', 'eventOcrAllowance', 'ocrUsage')",
            name=op.f("ck_credit_transactions_reason_allowed"),
        ),
        sa.CheckConstraint(
            "action IN ('grant', 'use')",
            name=op.f("ck_credit_transactions_action_allowed"),
        ),
        sa.CheckConstraint(
            "amount > 0",
            name=op.f("ck_credit_transactions_amount_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_transactions")),
    )
    op.create_index(
        op.f("ix_credit_transactions_user_id_feature_key_created_at_id"),
        "credit_transactions",
        ["user_id", "feature_key", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_credit_transactions_user_id_feature_key_created_at_id"),
        table_name="credit_transactions",
    )
    op.drop_table("credit_transactions")
    op.drop_table("user_credits")

"""extend credit source metadata

Revision ID: 20260703_0013
Revises: 20260703_0012
Create Date: 2026-07-03 00:13:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260703_0013"
down_revision: str | Sequence[str] | None = "20260703_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_credits",
        sa.Column("current_period", sa.String(length=7), nullable=True),
    )
    op.add_column(
        "credit_transactions",
        sa.Column("source_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "credit_transactions",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "credit_transactions",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_credit_transactions_source_type_allowed"),
        "credit_transactions",
        "source_type IS NULL "
        "OR source_type IN ('promotionRedemption', 'monthlyAllowance', 'ocrAnalysis')",
    )
    op.create_check_constraint(
        op.f("ck_credit_transactions_source_pair_complete"),
        "credit_transactions",
        "(source_type IS NULL AND source_id IS NULL) "
        "OR (source_type IS NOT NULL AND source_id IS NOT NULL)",
    )
    op.create_index(
        "ix_credit_transactions_idempotency_key_unique",
        "credit_transactions",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_credit_transactions_source_unique",
        "credit_transactions",
        ["source_type", "source_id", "user_id", "feature_key", "action"],
        unique=True,
        postgresql_where=sa.text("source_type IS NOT NULL AND source_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_credit_transactions_source_unique", table_name="credit_transactions")
    op.drop_index(
        "ix_credit_transactions_idempotency_key_unique",
        table_name="credit_transactions",
    )
    op.drop_constraint(
        op.f("ck_credit_transactions_source_pair_complete"),
        "credit_transactions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_credit_transactions_source_type_allowed"),
        "credit_transactions",
        type_="check",
    )
    op.drop_column("credit_transactions", "idempotency_key")
    op.drop_column("credit_transactions", "source_id")
    op.drop_column("credit_transactions", "source_type")
    op.drop_column("user_credits", "current_period")

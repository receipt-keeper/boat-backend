"""create receipts table

Revision ID: 20260625_0005
Revises: 20260624_0004
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260625_0005"
down_revision: str | Sequence[str] | None = "20260624_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("brand_name", sa.String(length=255), nullable=True),
        sa.Column("payment_location", sa.String(length=500), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=True),
        sa.Column("period_months", sa.Integer(), server_default="12", nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("memo", sa.String(length=1000), nullable=True),
        sa.Column(
            "requires_physical_receipt",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
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
            "period_months BETWEEN 1 AND 60",
            name=op.f("ck_receipts_period_months_range"),
        ),
        sa.CheckConstraint(
            "total_amount IS NULL OR total_amount >= 0",
            name=op.f("ck_receipts_total_amount_non_negative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts")),
    )
    op.create_index(op.f("ix_receipts_user_id"), "receipts", ["user_id"], unique=False)
    op.create_table(
        "receipt_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["receipts.id"],
            name=op.f("fk_receipt_attachments_receipt_id_receipts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipt_attachments")),
        sa.UniqueConstraint(
            "receipt_id",
            "file_id",
            name=op.f("uq_receipt_attachments_receipt_id_file_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("receipt_attachments")
    op.drop_index(op.f("ix_receipts_user_id"), table_name="receipts")
    op.drop_table("receipts")

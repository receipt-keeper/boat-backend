"""remove notification-owned fields from users

Revision ID: 20260627_0008
Revises: 20260626_0007
Create Date: 2026-06-27 00:08:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260627_0008"
down_revision: str | Sequence[str] | None = "20260626_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("user_push_tokens")
    op.drop_table("user_entitlements")
    op.drop_column("user_settings", "marketing_consent_updated_at")
    op.drop_column("user_settings", "marketing_consent")
    op.drop_column("user_settings", "notification_enabled")


def downgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("notification_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("marketing_consent", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("marketing_consent_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "user_entitlements",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "free_analysis_tokens_remaining",
            sa.Integer(),
            server_default="0",
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
            "free_analysis_tokens_remaining >= 0",
            name=op.f("ck_user_entitlements_free_analysis_tokens_remaining"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_entitlements_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_entitlements")),
    )
    op.create_table(
        "user_push_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=False),
        sa.Column("fcm_token", sa.String(length=512), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_push_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_push_tokens")),
        sa.UniqueConstraint("fcm_token", name=op.f("uq_user_push_tokens_fcm_token")),
        sa.UniqueConstraint(
            "user_id",
            "device_id",
            name=op.f("uq_user_push_tokens_user_id"),
        ),
    )

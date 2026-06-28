"""create notifications tables

Revision ID: 20260628_0009
Revises: 20260627_0008
Create Date: 2026-06-28 00:09:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260628_0009"
down_revision: str | Sequence[str] | None = "20260627_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_notifications")),
    )
    op.create_index(
        op.f("ix_user_notifications_user_id"),
        "user_notifications",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_notifications_user_id_created_at_id"),
        "user_notifications",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "notification_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "push_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "marketing_consent",
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
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_notification_settings")),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
    op.drop_index(
        op.f("ix_user_notifications_user_id_created_at_id"),
        table_name="user_notifications",
    )
    op.drop_index(op.f("ix_user_notifications_user_id"), table_name="user_notifications")
    op.drop_table("user_notifications")

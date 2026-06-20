"""extend auth and users account state

Revision ID: 20260620_0002
Revises: 20260614_0001
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260620_0002"
down_revision: str | None = "20260614_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("normalized_email", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("profile_image_url", sa.String(length=2048), nullable=True))
    op.create_index(
        "ix_users_normalized_email_unique",
        "users",
        ["normalized_email"],
        unique=True,
        postgresql_where=sa.text("normalized_email IS NOT NULL"),
    )

    op.add_column("external_identities", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column(
        "external_identities",
        sa.Column("normalized_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "external_identities",
        sa.Column("email_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credentials_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            ["credentials_id"],
            ["user_credentials.id"],
            name=op.f("fk_auth_sessions_credentials_id_user_credentials"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_refresh_tokens_session_id_auth_sessions"),
        "refresh_tokens",
        "auth_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "user_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "notification_enabled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "marketing_consent",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("terms_version", sa.String(length=50), nullable=True),
        sa.Column("privacy_version", sa.String(length=50), nullable=True),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marketing_consent_updated_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_user_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_settings")),
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


def downgrade() -> None:
    op.drop_table("user_push_tokens")
    op.drop_table("user_entitlements")
    op.drop_table("user_settings")
    op.drop_constraint(
        op.f("fk_refresh_tokens_session_id_auth_sessions"),
        "refresh_tokens",
        type_="foreignkey",
    )
    op.drop_column("refresh_tokens", "session_id")
    op.drop_table("auth_sessions")
    op.drop_column("external_identities", "email_verified")
    op.drop_column("external_identities", "normalized_email")
    op.drop_column("external_identities", "email")
    op.drop_index(
        "ix_users_normalized_email_unique",
        table_name="users",
        postgresql_where=sa.text("normalized_email IS NOT NULL"),
    )
    op.drop_column("users", "profile_image_url")
    op.drop_column("users", "normalized_email")

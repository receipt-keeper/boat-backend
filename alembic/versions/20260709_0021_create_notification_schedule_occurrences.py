from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260709_0021"
down_revision: str | Sequence[str] | None = "20260709_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_schedule_occurrences",
        sa.Column("campaign_key", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurrence_on", sa.Date(), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "campaign_key <> '' AND campaign_key = btrim(campaign_key)",
            name=op.f("ck_notification_schedule_occurrences_campaign_key"),
        ),
        sa.CheckConstraint(
            "target_type IN ('receipt', 'user')",
            name=op.f("ck_notification_schedule_occurrences_target_type"),
        ),
        sa.PrimaryKeyConstraint(
            "campaign_key",
            "target_type",
            "target_id",
            "occurrence_on",
            name=op.f("pk_notification_schedule_occurrences"),
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_schedule_occurrences")

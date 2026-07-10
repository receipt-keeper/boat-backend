from collections.abc import Sequence
from datetime import time

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.modules.notifications.schedule_rule_seed_data import (
    DEFAULT_NOTIFICATION_SCHEDULE_RULE_SEEDS,
    ScheduleRuleSeed,
)

revision: str = "20260709_0020"
down_revision: str | Sequence[str] | None = "20260707_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

type ScheduleRuleSeedValue = str | int | bool | time | None
type ScheduleRuleSeedRow = dict[str, ScheduleRuleSeedValue]


def _schedule_rule_seed_values(seed: ScheduleRuleSeed) -> ScheduleRuleSeedRow:
    return {
        "campaign_key": seed.campaign_key,
        "enabled": seed.enabled,
        "target_kind": seed.target_kind,
        "day_offset": seed.day_offset,
        "first_delay_days": seed.first_delay_days,
        "repeat_interval_days": seed.repeat_interval_days,
        "lookback_days": seed.lookback_days,
        "send_time_local": seed.send_time_local,
        "requires_marketing_consent": seed.requires_marketing_consent,
        "title_template": seed.title_template,
        "body_template": seed.body_template,
    }


_PM_SCHEDULE_RULES = tuple(
    _schedule_rule_seed_values(seed) for seed in DEFAULT_NOTIFICATION_SCHEDULE_RULE_SEEDS
)


def upgrade() -> None:
    op.create_table(
        "notification_schedule_rules",
        sa.Column("campaign_key", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("target_kind", sa.String(length=50), nullable=False),
        sa.Column("day_offset", sa.Integer(), nullable=True),
        sa.Column("first_delay_days", sa.Integer(), nullable=True),
        sa.Column("repeat_interval_days", sa.Integer(), nullable=True),
        sa.Column("lookback_days", sa.Integer(), nullable=True),
        sa.Column("send_time_local", sa.Time(timezone=False), nullable=False),
        sa.Column(
            "requires_marketing_consent",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("title_template", sa.String(length=100), nullable=False),
        sa.Column("body_template", sa.String(length=255), nullable=False),
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
        _check("campaign_key", "campaign_key <> '' AND campaign_key = btrim(campaign_key)"),
        _check(
            "target_kind",
            "target_kind IN ("
            "'warranty_receipt', "
            "'engagement_unregistered_receipt', "
            "'engagement_inactive_receipt', "
            "'engagement_all_user')",
        ),
        _check("day_offset", "day_offset IS NULL OR day_offset >= 0"),
        _check(
            "first_delay_days",
            "first_delay_days IS NULL OR first_delay_days >= 0",
        ),
        _check(
            "repeat_interval_days",
            "repeat_interval_days IS NULL OR repeat_interval_days >= 0",
        ),
        _check("lookback_days", "lookback_days IS NULL OR lookback_days >= 0"),
        _check(
            "warranty_timing",
            "target_kind <> 'warranty_receipt' OR "
            "(day_offset IS NOT NULL AND first_delay_days IS NULL "
            "AND repeat_interval_days IS NULL AND lookback_days IS NULL)",
        ),
        _check(
            "engagement_timing",
            "target_kind = 'warranty_receipt' OR repeat_interval_days IS NOT NULL",
        ),
        _check(
            "engagement_consent",
            "target_kind = 'warranty_receipt' OR requires_marketing_consent",
        ),
        sa.PrimaryKeyConstraint(
            "campaign_key",
            name=op.f("pk_notification_schedule_rules"),
        ),
    )
    _upsert_pm_schedule_rules()


def downgrade() -> None:
    op.drop_table("notification_schedule_rules")


def _upsert_pm_schedule_rules() -> None:
    table = sa.Table(
        "notification_schedule_rules",
        sa.MetaData(),
        autoload_with=op.get_bind(),
    )
    insert_statement = postgresql.insert(table).values(list(_PM_SCHEDULE_RULES))
    update_columns = tuple(name for name in _PM_SCHEDULE_RULES[0] if name != "campaign_key")
    op.get_bind().execute(
        insert_statement.on_conflict_do_update(
            index_elements=["campaign_key"],
            set_={
                **{
                    column_name: getattr(insert_statement.excluded, column_name)
                    for column_name in update_columns
                },
                "updated_at": sa.func.now(),
            },
        )
    )


def _check(name: str, condition: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        condition,
        name=op.f(f"ck_notification_schedule_rules_{name}"),
    )

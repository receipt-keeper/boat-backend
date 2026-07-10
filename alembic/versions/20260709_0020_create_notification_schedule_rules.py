from collections.abc import Sequence
from datetime import time
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260709_0020"
down_revision: str | Sequence[str] | None = "20260707_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PM_SCHEDULE_RULES: Final[tuple[dict[str, str | int | bool | time | None], ...]] = (
    {
        "campaign_key": "warranty_caution_d30",
        "enabled": True,
        "target_kind": "warranty_receipt",
        "day_offset": 30,
        "first_delay_days": None,
        "repeat_interval_days": None,
        "lookback_days": None,
        "send_time_local": time(9, 0),
        "requires_marketing_consent": False,
        "title_template": "보증 주의",
        "body_template": "[기기명] 무상 AS 30일 남았어요! 만료 전 서비스 센터 접수를 예약해보세요.",
    },
    {
        "campaign_key": "warranty_warning_d14",
        "enabled": True,
        "target_kind": "warranty_receipt",
        "day_offset": 14,
        "first_delay_days": None,
        "repeat_interval_days": None,
        "lookback_days": None,
        "send_time_local": time(9, 0),
        "requires_marketing_consent": False,
        "title_template": "보증 경고",
        "body_template": (
            "[기기명] 무상 AS 14일 남았어요! 기간 지나기 전 영수증 증빙 서류를 챙기세요."
        ),
    },
    {
        "campaign_key": "warranty_risk_d7",
        "enabled": True,
        "target_kind": "warranty_receipt",
        "day_offset": 7,
        "first_delay_days": None,
        "repeat_interval_days": None,
        "lookback_days": None,
        "send_time_local": time(9, 0),
        "requires_marketing_consent": False,
        "title_template": "보증 위험",
        "body_template": (
            "[기기명] 무상 AS 7일 남았어요! 일주일 뒤에는 무상 수리가 어려우니 서두르세요."
        ),
    },
    {
        "campaign_key": "warranty_expired_d0",
        "enabled": True,
        "target_kind": "warranty_receipt",
        "day_offset": 0,
        "first_delay_days": None,
        "repeat_interval_days": None,
        "lookback_days": None,
        "send_time_local": time(9, 0),
        "requires_marketing_consent": False,
        "title_template": "보증 완료",
        "body_template": "[기기명] 무상 AS 오늘이 만료예요! 마지막 무상 혜택 기회를 놓치지 마세요.",
    },
    {
        "campaign_key": "engagement_unregistered_receipt_after_7d",
        "enabled": True,
        "target_kind": "engagement_unregistered_receipt",
        "day_offset": None,
        "first_delay_days": 7,
        "repeat_interval_days": 7,
        "lookback_days": None,
        "send_time_local": time(9, 0),
        "requires_marketing_consent": True,
        "title_template": "상시 유도 1",
        "body_template": (
            "지갑 속에 방치해둔 가전제품 영수증이 있나요? 지금 등록하고 보증 기간을 챙기세요!"
        ),
    },
    {
        "campaign_key": "engagement_inactive_receipt_7d",
        "enabled": True,
        "target_kind": "engagement_inactive_receipt",
        "day_offset": None,
        "first_delay_days": None,
        "repeat_interval_days": 7,
        "lookback_days": 7,
        "send_time_local": time(9, 0),
        "requires_marketing_consent": True,
        "title_template": "상시 유도 2",
        "body_template": (
            "최근에 새로 구매한 전자기기가 있으신가요? 영수증 한 장으로 AS 만료일을 관리해보세요."
        ),
    },
    {
        "campaign_key": "engagement_all_users_14d",
        "enabled": True,
        "target_kind": "engagement_all_user",
        "day_offset": None,
        "first_delay_days": 14,
        "repeat_interval_days": 14,
        "lookback_days": None,
        "send_time_local": time(9, 0),
        "requires_marketing_consent": True,
        "title_template": "상시 유도 3",
        "body_template": (
            "지금 사용 가능한 무료 영수증 분석 기회가 남아있어요! 서랍 속 영수증을 스캔해보세요."
        ),
    },
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

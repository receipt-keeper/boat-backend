import anyio
import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text

from alembic import command
from app.core.config.settings import get_settings
from app.core.db.session import build_engine
from app.modules.notifications.tests.migration_support import (
    PROJECT_ROOT,
    alembic_config,
    table_column_names,
)

SCHEDULE_RULE_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260709_0020_create_notification_schedule_rules.py"
)
LEGACY_SCHEDULE_RULE_TABLE = "notification_campaign_policies"


def test_schedule_rule_migration_revision_is_linear() -> None:
    # Given: schedule rule migration 파일과 Alembic graph가 준비되어 있다.
    config = alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: migration 파일과 graph를 확인한다.
    heads = script_directory.get_heads()
    migration_source = SCHEDULE_RULE_MIGRATION_PATH.read_text(encoding="utf-8")

    # Then: graph는 단일 head이고 schedule rule migration은 이전 head 뒤에 온다.
    assert len(heads) == 1
    assert SCHEDULE_RULE_MIGRATION_PATH.is_file()
    assert 'revision: str = "20260709_0020"' in migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260707_0019"' in migration_source


def test_schedule_rule_migration_creates_exact_seeded_table(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = alembic_config()

    upgraded = False
    try:
        command.upgrade(config, "head")
        upgraded = True
        anyio.run(_assert_schedule_rule_table_seeded, postgres_async_database_url)
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _assert_schedule_rule_table_seeded(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            column_names = await table_column_names(
                connection,
                "notification_schedule_rules",
            )
            assert column_names == {
                "campaign_key",
                "enabled",
                "target_kind",
                "day_offset",
                "first_delay_days",
                "repeat_interval_days",
                "lookback_days",
                "send_time_local",
                "requires_marketing_consent",
                "title_template",
                "body_template",
                "created_at",
                "updated_at",
            }
            old_table_count = await connection.scalar(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :name"),
                {"name": LEGACY_SCHEDULE_RULE_TABLE},
            )
            assert old_table_count == 0
            primary_key_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM pg_constraint
                    WHERE conrelid = 'notification_schedule_rules'::regclass
                      AND conname = 'pk_notification_schedule_rules'
                      AND contype = 'p'
                    """
                )
            )
            assert primary_key_count == 1
            foreign_key_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM pg_constraint
                    WHERE conrelid = 'notification_schedule_rules'::regclass
                      AND contype = 'f'
                    """
                )
            )
            assert foreign_key_count == 0
            check_names = {
                row[0]
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT conname
                            FROM pg_constraint
                            WHERE conrelid = 'notification_schedule_rules'::regclass
                              AND contype = 'c'
                            """
                        )
                    )
                ).tuples()
            }
            assert {
                "ck_notification_schedule_rules_campaign_key",
                "ck_notification_schedule_rules_target_kind",
                "ck_notification_schedule_rules_day_offset",
                "ck_notification_schedule_rules_first_delay_days",
                "ck_notification_schedule_rules_repeat_interval_days",
                "ck_notification_schedule_rules_lookback_days",
                "ck_notification_schedule_rules_warranty_timing",
                "ck_notification_schedule_rules_engagement_timing",
            } <= check_names
            row_count = await connection.scalar(
                text("SELECT COUNT(*) FROM notification_schedule_rules")
            )
            assert row_count == 7
            warranty_offsets = (
                await connection.execute(
                    text(
                        """
                        SELECT campaign_key, day_offset
                        FROM notification_schedule_rules
                        WHERE target_kind = 'warranty_receipt'
                        ORDER BY campaign_key
                        """
                    )
                )
            ).mappings()
            assert {row["campaign_key"]: row["day_offset"] for row in warranty_offsets} == {
                "warranty_caution_d30": 30,
                "warranty_warning_d14": 14,
                "warranty_risk_d7": 7,
                "warranty_expired_d0": 0,
            }
    finally:
        await engine.dispose()

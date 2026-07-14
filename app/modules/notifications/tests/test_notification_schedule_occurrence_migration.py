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
from tests.support.database import configure_database_environment

OCCURRENCE_MIGRATION_PATH = (
    PROJECT_ROOT
    / "alembic"
    / "versions"
    / "20260709_0021_create_notification_schedule_occurrences.py"
)
LEGACY_OCCURRENCE_TABLE = "notification_scheduled_delivery_history"


def test_schedule_occurrence_migration_revision_is_linear() -> None:
    # Given: schedule occurrence migration 파일과 Alembic graph가 준비되어 있다.
    config = alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: migration 파일과 graph를 확인한다.
    heads = script_directory.get_heads()
    migration_source = OCCURRENCE_MIGRATION_PATH.read_text(encoding="utf-8")

    # Then: graph는 단일 head이고 occurrence migration은 schedule rule 뒤에 온다.
    assert len(heads) == 1
    assert OCCURRENCE_MIGRATION_PATH.is_file()
    assert 'revision: str = "20260709_0021"' in migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260709_0020"' in migration_source


def test_schedule_occurrence_migration_creates_composite_pk_without_foreign_keys(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_database_environment(monkeypatch, postgres_async_database_url)
    get_settings.cache_clear()
    config = alembic_config()

    upgraded = False
    try:
        command.upgrade(config, "head")
        upgraded = True
        anyio.run(_assert_schedule_occurrence_table_contract, postgres_async_database_url)
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _assert_schedule_occurrence_table_contract(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            column_names = await table_column_names(
                connection,
                "notification_schedule_occurrences",
            )
            assert column_names == {
                "campaign_key",
                "target_type",
                "target_id",
                "occurrence_on",
                "notification_id",
                "created_at",
            }
            notification_id_nullable = await connection.scalar(
                text(
                    """
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'notification_schedule_occurrences'
                      AND column_name = 'notification_id'
                    """
                )
            )
            assert notification_id_nullable == "YES"
            old_table_count = await connection.scalar(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :name"),
                {"name": LEGACY_OCCURRENCE_TABLE},
            )
            assert old_table_count == 0
            pk_columns = tuple(
                row[0]
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT a.attname
                            FROM pg_index i
                            JOIN pg_attribute a
                              ON a.attrelid = i.indrelid
                             AND a.attnum = ANY(i.indkey)
                            WHERE i.indrelid = 'notification_schedule_occurrences'::regclass
                              AND i.indisprimary
                            ORDER BY array_position(i.indkey, a.attnum)
                            """
                        )
                    )
                ).tuples()
            )
            assert pk_columns == ("campaign_key", "target_type", "target_id", "occurrence_on")
            foreign_key_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM pg_constraint
                    WHERE conrelid = 'notification_schedule_occurrences'::regclass
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
                            WHERE conrelid = 'notification_schedule_occurrences'::regclass
                              AND contype = 'c'
                            """
                        )
                    )
                ).tuples()
            }
            assert {
                "ck_notification_schedule_occurrences_campaign_key",
                "ck_notification_schedule_occurrences_target_type",
            } <= check_names
    finally:
        await engine.dispose()

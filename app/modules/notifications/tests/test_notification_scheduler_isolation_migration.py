import anyio
import pytest
from alembic.script import ScriptDirectory

from alembic import command
from app.core.config.settings import get_settings
from app.core.db.session import build_engine
from app.modules.notifications.tests.migration_support import (
    alembic_config,
    table_column_names,
)

SCHEDULER_INTERNAL_USER_NOTIFICATION_COLUMN = "scheduled_key"


def test_notification_schedule_migrations_have_single_head() -> None:
    # Given: current scheduler persistence includes the 0022 scheduler query indexes migration.
    config = alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: Alembic graph를 확인한다.
    heads = script_directory.get_heads()
    revisions = {revision.revision for revision in script_directory.walk_revisions()}

    # Then: scheduler migration graph는 0022를 단일 head로 두고 이전 revisions를 포함한다.
    assert heads == ["20260710_0022"]
    assert {"20260709_0020", "20260709_0021", "20260710_0022"} <= revisions


def test_user_notifications_schema_stays_scheduler_agnostic_after_head(
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
        anyio.run(
            _assert_user_notifications_schema_stays_scheduler_agnostic,
            postgres_async_database_url,
        )
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _assert_user_notifications_schema_stays_scheduler_agnostic(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            column_names = await table_column_names(connection, "user_notifications")
            assert SCHEDULER_INTERNAL_USER_NOTIFICATION_COLUMN not in column_names
    finally:
        await engine.dispose()

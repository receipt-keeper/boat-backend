from pathlib import Path

import anyio
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from alembic import command
from app.core.config.settings import get_settings
from app.core.db.session import build_engine

PROJECT_ROOT = Path(__file__).parents[4]
WITHDRAWN_IDENTITIES_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260712_0023_create_withdrawn_identities.py"
)


def test_withdrawn_identities_migration_revision_is_linear_after_scheduler_indexes() -> None:
    # Given: 0023 migration은 최신 head인 0022 뒤에 온다.
    config = _alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: Alembic revision graph와 0023 migration 파일을 확인한다.
    heads = script_directory.get_heads()

    # Then: revision graph는 단일 head를 유지하고 0023이 그 head다.
    assert len(heads) == 1
    assert heads[0] == "20260712_0023"
    assert WITHDRAWN_IDENTITIES_MIGRATION_PATH.is_file()

    migration_source = WITHDRAWN_IDENTITIES_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260712_0023"' in migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260710_0022"' in migration_source


def test_withdrawn_identities_migration_creates_tombstone_table(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 테스트 PostgreSQL DB와 Alembic 설정이 준비되어 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        # When: withdrawn_identities migration까지 upgrade한다.
        command.upgrade(config, "head")
        upgraded = True

        # Then: 테이블/컬럼/인덱스가 tombstone 계약과 일치한다.
        anyio.run(_assert_withdrawn_identities_table_is_constrained, postgres_async_database_url)
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _assert_withdrawn_identities_table_is_constrained(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            await _assert_columns(connection)
            await _assert_primary_key(connection)
            await _assert_expires_at_index(connection)
    finally:
        await engine.dispose()


async def _assert_columns(connection: AsyncConnection) -> None:
    columns = await connection.execute(
        text(
            """
            SELECT column_name, data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'withdrawn_identities'
            """
        )
    )
    column_contract = {row[0]: (row[1], row[2], row[3]) for row in columns.tuples()}
    assert column_contract == {
        "identity_hash": ("character varying", 64, "NO"),
        "withdrawn_at": ("timestamp with time zone", None, "NO"),
        "expires_at": ("timestamp with time zone", None, "NO"),
    }


async def _assert_primary_key(connection: AsyncConnection) -> None:
    primary_key_columns = await connection.execute(
        text(
            """
            SELECT key_usage.column_name
            FROM information_schema.table_constraints AS constraints
            JOIN information_schema.key_column_usage AS key_usage
              ON constraints.constraint_name = key_usage.constraint_name
             AND constraints.table_schema = key_usage.table_schema
            WHERE constraints.constraint_type = 'PRIMARY KEY'
              AND constraints.table_schema = 'public'
              AND constraints.table_name = 'withdrawn_identities'
            """
        )
    )
    assert [row[0] for row in primary_key_columns.tuples()] == ["identity_hash"]


async def _assert_expires_at_index(connection: AsyncConnection) -> None:
    index_rows = await connection.execute(
        text(
            """
            SELECT index_class.relname, array_agg(attribute.attname ORDER BY key.ordinality)
            FROM pg_index AS index_info
            JOIN pg_class AS table_class
              ON table_class.oid = index_info.indrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            JOIN pg_class AS index_class
              ON index_class.oid = index_info.indexrelid
            JOIN LATERAL unnest(index_info.indkey) WITH ORDINALITY AS key(attnum, ordinality)
              ON TRUE
            JOIN pg_attribute AS attribute
              ON attribute.attrelid = table_class.oid
             AND attribute.attnum = key.attnum
            WHERE namespace.nspname = 'public'
              AND table_class.relname = 'withdrawn_identities'
              AND index_info.indisprimary IS FALSE
            GROUP BY index_class.relname
            """
        )
    )
    indexes = {row[0]: tuple(row[1]) for row in index_rows.tuples()}
    assert indexes["ix_withdrawn_identities_expires_at"] == ("expires_at",)


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    config.set_main_option("path_separator", "os")
    return config

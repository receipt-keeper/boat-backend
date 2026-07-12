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
CREDIT_CLAIM_PURGE_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260712_0023_add_credit_transaction_purge_after.py"
)


def test_credit_claim_purge_migration_revision_is_linear_after_scheduler_indexes() -> None:
    # Given: 0023 migration은 최신 head인 0022 뒤에 온다.
    config = _alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: Alembic revision graph와 0023 migration 파일을 확인한다.
    heads = script_directory.get_heads()

    # Then: revision graph는 단일 head를 유지하고 0023이 그 head다.
    assert len(heads) == 1
    assert heads[0] == "20260712_0023"
    assert CREDIT_CLAIM_PURGE_MIGRATION_PATH.is_file()

    migration_source = CREDIT_CLAIM_PURGE_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260712_0023"' in migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260710_0022"' in migration_source


def test_credit_claim_purge_migration_adds_purge_after_column_and_index(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 테스트 PostgreSQL DB와 Alembic 설정이 준비되어 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        # When: purge_after 컬럼 migration까지 upgrade한다.
        command.upgrade(config, "head")
        upgraded = True

        # Then: 컬럼/인덱스가 claim 보존 상태 기계 계약과 일치한다.
        anyio.run(_assert_purge_after_column_is_constrained, postgres_async_database_url)
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _assert_purge_after_column_is_constrained(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            await _assert_withdrawn_identities_table_is_absent(connection)
            await _assert_purge_after_column(connection)
            await _assert_purge_after_index(connection)
    finally:
        await engine.dispose()


async def _assert_withdrawn_identities_table_is_absent(connection: AsyncConnection) -> None:
    exists = await connection.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'withdrawn_identities'
            )
            """
        )
    )
    assert exists is False


async def _assert_purge_after_column(connection: AsyncConnection) -> None:
    column = (
        await connection.execute(
            text(
                """
                SELECT data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'credit_transactions'
                  AND column_name = 'purge_after'
                """
            )
        )
    ).first()
    assert column is not None
    assert column[0] == "timestamp with time zone"
    assert column[1] == "YES"


async def _assert_purge_after_index(connection: AsyncConnection) -> None:
    index_row = (
        await connection.execute(
            text(
                """
                SELECT index_class.relname, pg_get_expr(index_info.indpred, index_info.indrelid)
                FROM pg_index AS index_info
                JOIN pg_class AS table_class
                  ON table_class.oid = index_info.indrelid
                JOIN pg_namespace AS namespace
                  ON namespace.oid = table_class.relnamespace
                JOIN pg_class AS index_class
                  ON index_class.oid = index_info.indexrelid
                WHERE namespace.nspname = 'public'
                  AND table_class.relname = 'credit_transactions'
                  AND index_class.relname = 'ix_credit_transactions_purge_after'
                """
            )
        )
    ).first()
    assert index_row is not None
    assert index_row[1] == "(purge_after IS NOT NULL)"


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    config.set_main_option("path_separator", "os")
    return config

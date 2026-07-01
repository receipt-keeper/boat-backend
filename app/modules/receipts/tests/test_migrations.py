import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.core.config.settings import get_settings
from app.core.db.session import build_engine


def test_receipts_migration_creates_receipt_tables(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    project_root = Path(__file__).parents[4]
    config = Config()
    config.set_main_option("script_location", str(project_root / "alembic"))
    config.set_main_option("prepend_sys_path", str(project_root))
    config.set_main_option("path_separator", "os")

    upgraded = False
    try:
        command.upgrade(config, "head")
        upgraded = True
        asyncio.run(_assert_tables_exist(postgres_async_database_url))
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _assert_tables_exist(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            for table_name in ("receipts", "receipt_attachments"):
                result = await connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_name = :table_name
                        )
                        """
                    ),
                    {"table_name": table_name},
                )
                assert result.scalar_one() is True
            column_type = await connection.scalar(
                text(
                    """
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'receipts'
                      AND column_name = 'total_amount'
                    """
                )
            )
            assert column_type == "bigint"
            sub_category_column_type = await connection.scalar(
                text(
                    """
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'receipts'
                      AND column_name = 'sub_category'
                    """
                )
            )
            assert sub_category_column_type == "character varying"
    finally:
        await engine.dispose()

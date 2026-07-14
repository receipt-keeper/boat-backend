import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.core.config.settings import get_settings
from app.core.db.session import build_engine
from tests.support.database import configure_database_environment

_PRE_CATEGORY_ENUM_REVISION = "20260710_0022"


def test_receipts_migration_creates_receipt_tables(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_database_environment(monkeypatch, postgres_async_database_url)
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
            expected_column_types = {
                "total_amount": "bigint",
                "category": "USER-DEFINED",
                "sub_category": "character varying",
                "serial_number": "character varying",
            }
            for column_name, expected_type in expected_column_types.items():
                column_type = await connection.scalar(
                    text(
                        """
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'receipts'
                          AND column_name = :column_name
                        """
                    ),
                    {"column_name": column_name},
                )
                assert column_type == expected_type
    finally:
        await engine.dispose()


def test_receipt_category_enum_migration_normalizes_legacy_values(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_database_environment(monkeypatch, postgres_async_database_url)
    get_settings.cache_clear()
    project_root = Path(__file__).parents[4]
    config = Config()
    config.set_main_option("script_location", str(project_root / "alembic"))
    config.set_main_option("prepend_sys_path", str(project_root))
    config.set_main_option("path_separator", "os")

    upgraded = False
    try:
        command.upgrade(config, _PRE_CATEGORY_ENUM_REVISION)
        upgraded = True
        asyncio.run(_insert_legacy_categories(postgres_async_database_url))

        command.upgrade(config, "head")
        asyncio.run(_assert_category_enum_values(postgres_async_database_url))

        command.downgrade(config, _PRE_CATEGORY_ENUM_REVISION)
        asyncio.run(_assert_category_downgrade_values(postgres_async_database_url))
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _insert_legacy_categories(database_url: str) -> None:
    categories = {
        "01-kitchen": "주방가전",
        "02-laundry": "세탁/청소",
        "03-living": "리빙/냉난방",
        "04-it-product": "IT 제품",
        "05-video-it": "영상/IT 제품",
        "06-other-product": "기타 제품",
        "07-unknown": "깨진 분류값",
        "08-null": None,
    }
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            for item_name, category in categories.items():
                await connection.execute(
                    text(
                        """
                        INSERT INTO receipts (
                            id, user_id, item_name, payment_date, period_months,
                            expires_on, category, requires_physical_receipt
                        )
                        VALUES (
                            :id, :user_id, :item_name, DATE '2026-01-01', 12,
                            DATE '2027-01-01', :category, false
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "user_id": uuid4(),
                        "item_name": item_name,
                        "category": category,
                    },
                )
    finally:
        await engine.dispose()


async def _assert_category_enum_values(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text("SELECT item_name, category::text AS category FROM receipts")
                )
            ).mappings()
            values = {row["item_name"]: row["category"] for row in rows}
            assert values == {
                "01-kitchen": "kitchen_appliance",
                "02-laundry": "laundry_cleaning",
                "03-living": "living_climate",
                "04-it-product": "it_device",
                "05-video-it": "it_device",
                "06-other-product": "other_device",
                "07-unknown": "other_device",
                "08-null": None,
            }
            enum_labels = (
                await connection.execute(
                    text(
                        """
                        SELECT enumlabel
                        FROM pg_enum
                        JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
                        WHERE pg_type.typname = 'receipt_category'
                        ORDER BY enumsortorder
                        """
                    )
                )
            ).scalars()
            assert list(enum_labels) == [
                "kitchen_appliance",
                "laundry_cleaning",
                "living_climate",
                "it_device",
                "other_device",
            ]
    finally:
        await engine.dispose()


async def _assert_category_downgrade_values(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            column_type = await connection.scalar(
                text(
                    """
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'receipts'
                      AND column_name = 'category'
                    """
                )
            )
            assert column_type == "character varying"
            values = set(
                (
                    await connection.execute(
                        text("SELECT category FROM receipts WHERE category IS NOT NULL")
                    )
                ).scalars()
            )
            assert values == {
                "kitchen_appliance",
                "laundry_cleaning",
                "living_climate",
                "it_device",
                "other_device",
            }
    finally:
        await engine.dispose()

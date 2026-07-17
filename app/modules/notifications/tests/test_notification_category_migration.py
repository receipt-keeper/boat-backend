from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import anyio
import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.core.config.settings import get_settings
from app.core.db.session import build_engine
from tests.support.database import configure_database_environment

PROJECT_ROOT = Path(__file__).parents[4]
_GENERALIZE_REVISION = "20260705_0013"


def test_notification_category_migration_uses_literal_warranty_prefix(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 구 스키마에 warranty 문자열로 시작하지만 '_'가 없는 kind가 있다.
    configure_database_environment(monkeypatch, postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()
    row_id = uuid4()
    inserted = False
    upgraded = False
    try:
        command.upgrade(config, _GENERALIZE_REVISION)
        upgraded = True
        anyio.run(_insert_legacy_warranty_like_row, postgres_async_database_url, row_id)
        inserted = True

        # When: 알림 카테고리 migration을 적용한다.
        command.upgrade(config, "head")

        # Then: wildcard lookalike kind는 제품 관리 코드로 남는다.
        assert (
            anyio.run(
                _read_category,
                postgres_async_database_url,
                row_id,
            )
            == "product_management"
        )
    finally:
        if inserted:
            anyio.run(_delete_row, postgres_async_database_url, row_id)
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _insert_legacy_warranty_like_row(database_url: str, row_id: UUID) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_notifications
                        (id, user_id, message_type, kind, title, message,
                         resource_type, resource_id, created_at)
                    VALUES
                        (:id, :user_id, 'transactional', 'warrantySale',
                         '알림', 'message', NULL, NULL, :created_at)
                    """
                ),
                {
                    "id": row_id,
                    "user_id": uuid4(),
                    "created_at": datetime.now(UTC),
                },
            )
    finally:
        await engine.dispose()


async def _read_category(database_url: str, row_id: UUID) -> str:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            category = await connection.scalar(
                text("SELECT category FROM user_notifications WHERE id = :id"),
                {"id": row_id},
            )
            assert isinstance(category, str)
            return category
    finally:
        await engine.dispose()


async def _delete_row(database_url: str, row_id: UUID) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM user_notifications WHERE id = :id"),
                {"id": row_id},
            )
    finally:
        await engine.dispose()


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    config.set_main_option("path_separator", "os")
    return config

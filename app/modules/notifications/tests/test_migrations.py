from pathlib import Path
from uuid import UUID, uuid4

import anyio
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from alembic import command
from app.core.config.settings import get_settings
from app.core.db.session import build_engine
from app.modules.notifications.tests.migration_notification_table_contract import (
    assert_backfill_is_correct,
    insert_legacy_notification_rows,
)

PROJECT_ROOT = Path(__file__).parents[4]
GENERALIZE_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260705_0013_generalize_user_notifications.py"
)
PUSH_TOKENS_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260704_0012_create_user_push_tokens_table.py"
)
RENAME_TOKEN_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260705_0014_rename_user_push_tokens_fid_to_token.py"
)

_PRE_MIGRATION_REVISION = "20260704_0012"
_GENERALIZE_REVISION = "20260705_0013"
_HEAD_REVISION = "20260705_0014"


def test_generalize_notifications_migration_revision_is_linear() -> None:
    # Given: 알림 일반화 migration은 user push tokens migration 뒤에 온다.
    config = _alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: Alembic revision graph와 migration 파일을 확인한다.
    heads = script_directory.get_heads()

    # Then: revision graph는 단일 head를 유지하고 체인은 선형이다.
    assert len(heads) == 1
    assert heads[0] == _HEAD_REVISION
    assert GENERALIZE_MIGRATION_PATH.is_file()
    assert PUSH_TOKENS_MIGRATION_PATH.is_file()
    assert RENAME_TOKEN_MIGRATION_PATH.is_file()

    migration_source = GENERALIZE_MIGRATION_PATH.read_text(encoding="utf-8")
    assert f'revision: str = "{_GENERALIZE_REVISION}"' in migration_source
    assert (
        f'down_revision: str | Sequence[str] | None = "{_PRE_MIGRATION_REVISION}"'
        in migration_source
    )

    push_tokens_migration_source = PUSH_TOKENS_MIGRATION_PATH.read_text(encoding="utf-8")
    assert f'revision: str = "{_PRE_MIGRATION_REVISION}"' in push_tokens_migration_source

    rename_token_migration_source = RENAME_TOKEN_MIGRATION_PATH.read_text(encoding="utf-8")
    assert f'revision: str = "{_HEAD_REVISION}"' in rename_token_migration_source
    assert (
        f'down_revision: str | Sequence[str] | None = "{_GENERALIZE_REVISION}"'
        in rename_token_migration_source
    )


def test_generalize_notifications_migration_backfills_legacy_rows(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 테스트 PostgreSQL DB와 Alembic 설정이 준비되어 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        # When: 구형 스키마(20260704_0012)까지 올리고 대표 데이터를 삽입한다.
        command.upgrade(config, _PRE_MIGRATION_REVISION)
        upgraded = True
        row_ids = anyio.run(_insert_legacy_rows, postgres_async_database_url)

        # And: head(20260705_0014)로 upgrade한다.
        command.upgrade(config, "head")

        # Then: message_type/title/resource backfill과 제약조건이 계약과 일치한다.
        anyio.run(assert_backfill_is_correct, postgres_async_database_url, row_ids)
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


def test_generalize_notifications_migration_downgrade_round_trip(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: head까지 올라간 상태에서 대표 데이터가 채워져 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        command.upgrade(config, _PRE_MIGRATION_REVISION)
        upgraded = True
        anyio.run(_insert_legacy_rows, postgres_async_database_url)
        command.upgrade(config, "head")

        # When: downgrade로 이전 리비전까지 내린다.
        command.downgrade(config, _PRE_MIGRATION_REVISION)

        # Then: target_type/target_id가 복원되고 message_type/title 컬럼은 사라진다.
        anyio.run(_assert_downgrade_restored_legacy_columns, postgres_async_database_url)

        # And: 다시 head로 upgrade해도 성공한다.
        command.upgrade(config, "head")
        anyio.run(_assert_head_columns_present, postgres_async_database_url)
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


def test_generalize_notifications_migration_downgrade_normalizes_opaque_values(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: head 스키마에 새 API가 수용한 불투명 값 행이 존재한다 —
    # 구 enum 밖 resource_type('file') 행과 구 enum 밖 kind('ocr_completed') 행.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        command.upgrade(config, "head")
        upgraded = True
        opaque_resource_row_id, opaque_kind_row_id = anyio.run(
            _insert_head_rows_with_opaque_values, postgres_async_database_url
        )

        # When/Then: 구 enum 밖 kind가 남아 있으면 downgrade는 명시적으로 실패하고
        # 스키마는 head 상태를 유지한다.
        with pytest.raises(RuntimeError, match="kind"):
            command.downgrade(config, _PRE_MIGRATION_REVISION)
        anyio.run(_assert_head_columns_present, postgres_async_database_url)

        # And: 문제 행을 정리하면 downgrade가 성공하고, 구 enum 밖 resource_type은
        # 구 코드가 읽을 수 있는 '대상 없음'('none')으로 정규화된다.
        anyio.run(_delete_notification_row, postgres_async_database_url, opaque_kind_row_id)
        command.downgrade(config, _PRE_MIGRATION_REVISION)
        anyio.run(
            _assert_opaque_resource_row_normalized,
            postgres_async_database_url,
            opaque_resource_row_id,
        )
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _insert_legacy_rows(database_url: str) -> dict[str, UUID]:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            return await insert_legacy_notification_rows(connection)
    finally:
        await engine.dispose()


async def _assert_downgrade_restored_legacy_columns(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            column_names = await _column_names(connection)
            assert "target_type" in column_names
            assert "target_id" in column_names
            assert "resource_type" not in column_names
            assert "resource_id" not in column_names
            assert "message_type" not in column_names
            assert "title" not in column_names
            assert "metadata" not in column_names

            # receiptUpload/none 구분은 소실되어 전부 'none'으로 복원된다(비가역, docstring 명시).
            target_type_values = await connection.execute(
                text(
                    """
                    SELECT DISTINCT target_type
                    FROM user_notifications
                    WHERE target_id IS NULL
                    """
                )
            )
            distinct_null_id_target_types = {row[0] for row in target_type_values.tuples()}
            assert distinct_null_id_target_types == {"none"}

            # ('receipt', uuid) 행은 그대로 복원되어 있어야 한다.
            receipt_row_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM user_notifications
                    WHERE target_type = 'receipt' AND target_id IS NOT NULL
                    """
                )
            )
            assert receipt_row_count is not None
            assert receipt_row_count > 0
    finally:
        await engine.dispose()


async def _insert_head_rows_with_opaque_values(database_url: str) -> tuple[UUID, UUID]:
    opaque_resource_row_id = uuid4()
    opaque_kind_row_id = uuid4()
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_notifications
                        (id, user_id, message_type, kind, title, message,
                         resource_type, resource_id)
                    VALUES
                        (:opaque_resource_id, :user_id, 'transactional', 'warranty_risk',
                         '보증 만료 임박', '냉장고 보증이 30일 뒤 만료돼요', 'file', :resource_id),
                        (:opaque_kind_id, :user_id, 'transactional', 'ocr_completed',
                         '영수증 분석 완료', '영수증 정보가 등록됐어요', NULL, NULL)
                    """
                ),
                {
                    "opaque_resource_id": opaque_resource_row_id,
                    "opaque_kind_id": opaque_kind_row_id,
                    "user_id": uuid4(),
                    "resource_id": uuid4(),
                },
            )
    finally:
        await engine.dispose()
    return opaque_resource_row_id, opaque_kind_row_id


async def _delete_notification_row(database_url: str, row_id: UUID) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM user_notifications WHERE id = :id"),
                {"id": row_id},
            )
    finally:
        await engine.dispose()


async def _assert_opaque_resource_row_normalized(database_url: str, row_id: UUID) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT target_type, target_id FROM user_notifications WHERE id = :id"),
                    {"id": row_id},
                )
            ).one()
            assert row.target_type == "none"
            assert row.target_id is None
    finally:
        await engine.dispose()


async def _assert_head_columns_present(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            column_names = await _column_names(connection)
            assert "message_type" in column_names
            assert "title" in column_names
            assert "resource_type" in column_names
            assert "resource_id" in column_names
            assert "metadata" in column_names
            assert "target_type" not in column_names
            assert "target_id" not in column_names
    finally:
        await engine.dispose()


async def _column_names(connection: AsyncConnection) -> set[str]:
    result = await connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'user_notifications'
            """
        )
    )
    return {row[0] for row in result.tuples()}


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    config.set_main_option("path_separator", "os")
    return config

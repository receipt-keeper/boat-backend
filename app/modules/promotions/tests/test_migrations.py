from pathlib import Path

import anyio
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.core.config.settings import get_settings
from app.core.db.session import build_engine
from app.modules.promotions.tests.migration_promotion_table_contract import (
    assert_promotion_tables_are_constrained,
)

PROJECT_ROOT = Path(__file__).parents[4]
PROMOTION_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260705_0016_create_promotion_tables.py"
)
CREDIT_SOURCE_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260705_0017_extend_credit_source_metadata.py"
)
PROMOTION_CONTENT_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260705_0018_create_promotion_contents.py"
)
PROMOTION_CONTEXT_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260707_0019_add_promotion_context.py"
)


def test_promotion_migration_revision_is_linear_through_context_extension() -> None:
    # Given: Promotion persistence migration 뒤에 credit source와 content migration이 이어진다.
    config = _alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: Alembic revision graph와 Promotion 관련 migration 파일을 확인한다.
    heads = script_directory.get_heads()

    # Then: 단일 head는 context migration이고 down_revision은 content migration이다.
    assert heads == ["20260707_0019"]
    assert PROMOTION_MIGRATION_PATH.is_file()
    assert CREDIT_SOURCE_MIGRATION_PATH.is_file()
    assert PROMOTION_CONTENT_MIGRATION_PATH.is_file()
    assert PROMOTION_CONTEXT_MIGRATION_PATH.is_file()

    migration_source = PROMOTION_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260705_0016"' in migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260705_0015"' in migration_source
    credit_source = CREDIT_SOURCE_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'down_revision: str | Sequence[str] | None = "20260705_0016"' in credit_source
    promotion_content = PROMOTION_CONTENT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260705_0018"' in promotion_content
    assert 'down_revision: str | Sequence[str] | None = "20260705_0017"' in promotion_content
    promotion_context = PROMOTION_CONTEXT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260707_0019"' in promotion_context
    assert 'down_revision: str | Sequence[str] | None = "20260705_0018"' in promotion_context


def test_promotion_migration_creates_constrained_tables(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 테스트 PostgreSQL DB와 Alembic 설정이 준비되어 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        # When: 최신 migration까지 upgrade한다.
        command.upgrade(config, "head")
        upgraded = True

        # Then: Promotion 테이블/제약/insert behavior가 T1 계약과 일치한다.
        anyio.run(assert_promotion_tables_are_constrained, postgres_async_database_url)
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


def test_promotion_migration_rejects_invalid_context_schema_inputs(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 최신 migration이 적용된 테스트 DB가 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        command.upgrade(config, "head")
        upgraded = True

        # When: invalid/duplicate insert probe를 실행한다.
        observed_failures = anyio.run(
            assert_promotion_tables_are_constrained,
            postgres_async_database_url,
        )

        # Then: DB가 각 제약 위반을 실제로 거절한다.
        for failure in observed_failures:
            print(failure)
        assert len(observed_failures) == 7
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


def test_promotion_contents_reject_duplicate_promotion_content(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 최신 migration이 적용된 테스트 DB와 기존 프로모션이 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        command.upgrade(config, "head")
        upgraded = True

        # When: 같은 promotion_id로 content row를 두 번 저장한다.
        failure = anyio.run(
            _duplicate_promotion_content_failure,
            postgres_async_database_url,
        )

        # Then: DB unique constraint가 실제 중복 저장을 거절한다.
        assert "uq_promotion_contents_promotion_id" in failure
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


async def _duplicate_promotion_content_failure(database_url: str) -> str:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO promotions (
                        id,
                        name,
                        active,
                        starts_at,
                        benefit_feature_key,
                        benefit_amount
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000401',
                        'content duplicate target',
                        true,
                        now(),
                        'ocr',
                        10
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO promotion_contents (
                        id,
                        promotion_id,
                        banner_image_url
                    )
                    VALUES (
                        '00000000-0000-0000-0000-000000000501',
                        '00000000-0000-0000-0000-000000000401',
                        '/files/00000000-0000-0000-0000-000000000901/content'
                    )
                    """
                )
            )
            with pytest.raises(DBAPIError) as exc_info:
                await connection.execute(
                    text(
                        """
                        INSERT INTO promotion_contents (
                            id,
                            promotion_id,
                            banner_image_url
                        )
                        VALUES (
                            '00000000-0000-0000-0000-000000000502',
                            '00000000-0000-0000-0000-000000000401',
                            '/files/00000000-0000-0000-0000-000000000902/content'
                        )
                        """
                    )
                )
            return str(exc_info.value.orig)
    finally:
        await engine.dispose()


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    config.set_main_option("path_separator", "os")
    return config

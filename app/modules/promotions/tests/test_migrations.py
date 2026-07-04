from pathlib import Path

import anyio
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from app.core.config.settings import get_settings
from app.modules.promotions.tests.migration_promotion_table_contract import (
    assert_promotion_tables_are_constrained,
)

PROJECT_ROOT = Path(__file__).parents[4]
PROMOTION_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260703_0012_create_promotion_tables.py"
)
CREDIT_SOURCE_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260703_0013_extend_credit_source_metadata.py"
)


def test_promotion_migration_revision_is_linear_before_credit_source_extension() -> None:
    # Given: Promotion persistence migration 뒤에 credit source metadata migration이 이어진다.
    config = _alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: Alembic revision graph와 Promotion migration 파일을 확인한다.
    heads = script_directory.get_heads()

    # Then: 단일 head는 최신 credit source migration이고 Promotion migration은 직전 revision이다.
    assert heads == ["20260703_0013"]
    assert PROMOTION_MIGRATION_PATH.is_file()
    assert CREDIT_SOURCE_MIGRATION_PATH.is_file()

    migration_source = PROMOTION_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260703_0012"' in migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260702_0011"' in migration_source
    credit_source = CREDIT_SOURCE_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'down_revision: str | Sequence[str] | None = "20260703_0012"' in credit_source


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


def test_promotion_migration_rejects_invalid_schema_inputs(
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
        assert len(observed_failures) == 6
    finally:
        if upgraded:
            command.downgrade(config, "base")
        get_settings.cache_clear()


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    config.set_main_option("path_separator", "os")
    return config

from pathlib import Path

import anyio
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from app.core.config.settings import get_settings
from app.modules.credits.tests.migration_credit_table_contract import (
    assert_credit_tables_are_constrained,
)

PROJECT_ROOT = Path(__file__).parents[4]
CREDIT_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260701_0011_create_credit_tables.py"
)
RECEIPT_SERIAL_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260702_0011_add_receipt_serial_number.py"
)
PROMOTION_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260705_0016_create_promotion_tables.py"
)
CREDIT_SOURCE_MIGRATION_PATH = (
    PROJECT_ROOT / "alembic" / "versions" / "20260705_0017_extend_credit_source_metadata.py"
)


def test_credit_source_migration_revision_is_linear_after_promotion_tables() -> None:
    # Given: T3 credit source migration은 T1 promotion persistence migration 뒤에 온다.
    config = _alembic_config()
    script_directory = ScriptDirectory.from_config(config)

    # When: Alembic revision graph와 T3 migration 파일을 확인한다.
    heads = script_directory.get_heads()

    # Then: revision graph는 단일 head를 유지하고 credit migration 체인은 그대로 남는다.
    assert len(heads) == 1
    assert CREDIT_MIGRATION_PATH.is_file()
    assert RECEIPT_SERIAL_MIGRATION_PATH.is_file()
    assert PROMOTION_MIGRATION_PATH.is_file()
    assert CREDIT_SOURCE_MIGRATION_PATH.is_file()

    migration_source = CREDIT_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260701_0011"' in migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260701_0010"' in migration_source

    receipt_serial_migration_source = RECEIPT_SERIAL_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260702_0011"' in receipt_serial_migration_source
    assert (
        'down_revision: str | Sequence[str] | None = "20260701_0011"'
        in receipt_serial_migration_source
    )

    promotion_migration_source = PROMOTION_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260705_0016"' in promotion_migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260705_0015"' in (
        promotion_migration_source
    )

    credit_source_migration_source = CREDIT_SOURCE_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "20260705_0017"' in credit_source_migration_source
    assert 'down_revision: str | Sequence[str] | None = "20260705_0016"' in (
        credit_source_migration_source
    )


def test_credits_migration_creates_credit_tables(
    postgres_async_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 테스트 PostgreSQL DB와 Alembic 설정이 준비되어 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()
    config = _alembic_config()

    upgraded = False
    try:
        # When: credit ledger migration까지 upgrade한다.
        command.upgrade(config, "head")
        upgraded = True

        # Then: 테이블/제약/insert behavior가 OCR ledger 계약과 일치한다.
        anyio.run(assert_credit_tables_are_constrained, postgres_async_database_url)
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

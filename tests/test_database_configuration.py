from pathlib import Path

import anyio
import pytest
from alembic.config import Config
from pydantic import SecretStr, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import URL
from testcontainers.postgres import PostgresContainer

from alembic import command
from app.core.config.settings import Settings, get_settings
from app.core.db.session import build_engine
from tests.support.database import (
    configure_database_environment,
    database_url_from_postgres_container,
)

PROJECT_ROOT = Path(__file__).parents[1]


def test_settings_builds_database_url_from_raw_components() -> None:
    credential_value = "p@ss:/%#word"

    settings = Settings(
        db_host="db.internal",
        db_port=5432,
        db_name="boat",
        db_user="boat",
        db_password=SecretStr(credential_value),
    )

    database_url = settings.database_url

    assert isinstance(database_url, URL)
    assert database_url.drivername == "postgresql+asyncpg"
    assert database_url.host == "db.internal"
    assert database_url.port == 5432
    assert database_url.database == "boat"
    assert database_url.username == "boat"
    assert database_url.password == credential_value


def test_settings_requires_component_database_contract_without_database_url_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://legacy:legacy@localhost:5432/legacy")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    missing_fields = {str(error["loc"][0]) for error in exc_info.value.errors()}
    assert missing_fields == {"db_host", "db_port", "db_name", "db_user", "db_password"}


@pytest.mark.parametrize("port", [0, 65536])
def test_settings_rejects_out_of_range_database_port(port: int) -> None:
    with pytest.raises(ValidationError, match="db_port"):
        Settings(
            db_host="localhost",
            db_port=port,
            db_name="boat",
            db_user="boat",
            db_password=SecretStr("boat"),
        )


def test_settings_rejects_non_numeric_database_port_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "not-a-port")
    monkeypatch.setenv("DB_NAME", "boat")
    monkeypatch.setenv("DB_USER", "boat")
    monkeypatch.setenv("DB_PASSWORD", "boat")

    with pytest.raises(ValidationError, match="db_port"):
        Settings()


def test_alembic_upgrade_accepts_reserved_password_without_configparser_interpolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_value = "p@ss:/%#word"

    with PostgresContainer(
        "postgres:16",
        username="boat",
        password=credential_value,
        dbname="boat",
        driver=None,
    ) as postgres:
        database_url = database_url_from_postgres_container(postgres)
        configure_database_environment(monkeypatch, database_url)
        get_settings.cache_clear()
        config = Config()
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
        config.set_main_option("path_separator", "os")

        upgraded = False
        try:
            # Given: 예약 문자가 있는 raw DB_PASSWORD와 개별 DB 환경변수가 설정되어 있다.
            # When: offline SQL 생성과 실제 PostgreSQL online upgrade를 순서대로 실행한다.
            command.upgrade(config, "20260707_0019", sql=True)
            command.upgrade(config, "head")
            upgraded = True
            anyio.run(_assert_select_one, database_url)
            # Then: ConfigParser를 거치지 않고 두 경로 모두 성공한다.
        finally:
            if upgraded:
                command.downgrade(config, "base")
            get_settings.cache_clear()


async def _assert_select_one(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await engine.dispose()

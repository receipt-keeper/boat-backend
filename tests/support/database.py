import pytest
from sqlalchemy.engine import make_url
from testcontainers.postgres import PostgresContainer

from app.core.config.settings import build_database_url


def database_url_from_postgres_container(postgres: PostgresContainer) -> str:
    return build_database_url(
        host=postgres.get_container_host_ip(),
        port=postgres.get_exposed_port(postgres.port),
        database=postgres.dbname,
        username=postgres.username,
        password=postgres.password,
    ).render_as_string(hide_password=False)


def configure_database_environment(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    parsed_url = make_url(database_url)
    host = parsed_url.host
    port = parsed_url.port
    database = parsed_url.database
    username = parsed_url.username
    password = parsed_url.password
    assert host is not None
    assert port is not None
    assert database is not None
    assert username is not None
    assert password is not None

    monkeypatch.setenv("DB_HOST", host)
    monkeypatch.setenv("DB_PORT", str(port))
    monkeypatch.setenv("DB_NAME", database)
    monkeypatch.setenv("DB_USER", username)
    monkeypatch.setenv("DB_PASSWORD", password)

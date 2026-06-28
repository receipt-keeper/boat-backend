from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Final
from uuid import UUID

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from app.core.config.settings import Settings
from app.core.db.base import Base
from app.core.db.session import build_engine, build_session_factory
from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import create_app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.notifications.infrastructure.persistence import orm as _notifications_orm

_ = _notifications_orm

TEST_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000101")
TEST_CREDENTIALS_ID: Final = UUID("00000000-0000-0000-0000-000000000102")
TEST_SESSION_ID: Final = UUID("00000000-0000-0000-0000-000000000103")
OTHER_USER_ID: Final = UUID("00000000-0000-0000-0000-000000000201")
OTHER_CREDENTIALS_ID: Final = UUID("00000000-0000-0000-0000-000000000202")
OTHER_SESSION_ID: Final = UUID("00000000-0000-0000-0000-000000000203")
MISSING_NOTIFICATION_ID: Final = UUID("00000000-0000-0000-0000-000000000999")
TEST_SETTINGS: Final = Settings(
    jwt_secret_key="x" * 48,
    jwt_issuer="boat-backend-test",
    jwt_audience="boat-api-test",
)


def _principal_for_user(user_id: UUID) -> AuthenticatedPrincipal:
    if user_id == OTHER_USER_ID:
        return AuthenticatedPrincipal(
            user_id=OTHER_USER_ID,
            credentials_id=OTHER_CREDENTIALS_ID,
            session_id=OTHER_SESSION_ID,
            role="user",
        )

    return AuthenticatedPrincipal(
        user_id=user_id,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )


def _authenticate_current_principal_for(
    user_id: UUID,
) -> Callable[[Request], Awaitable[AuthenticatedPrincipal]]:
    async def authenticate(request: Request) -> AuthenticatedPrincipal:
        principal = _principal_for_user(user_id)
        set_current_principal(request, principal)
        return principal

    return authenticate


@pytest.fixture(scope="module")
def postgres_async_database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver=None) as postgres:
        database_url = postgres.get_connection_url()
        yield database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture
async def postgres_session_factory(
    postgres_async_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(postgres_async_database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield build_session_factory(engine)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@asynccontextmanager
async def notification_api_client(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID = TEST_USER_ID,
) -> AsyncIterator[AsyncClient]:
    test_app = create_app(TEST_SETTINGS)
    test_app.state.session_factory = session_factory
    test_app.dependency_overrides[authenticate_current_principal] = (
        _authenticate_current_principal_for(user_id)
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        test_app.dependency_overrides.clear()

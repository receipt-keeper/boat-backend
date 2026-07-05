from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from app.core.db.base import Base
from app.core.db.session import build_engine, build_session_factory


@pytest.fixture(scope="module")
def postgres_async_database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver=None) as postgres:
        database_url = postgres.get_connection_url()
        yield database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture
async def postgres_session_factory(
    postgres_async_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from app.modules.promotions.infrastructure.persistence import orm as promotions_orm

    _ = promotions_orm.Promotion
    _ = promotions_orm.PromotionContent
    _ = promotions_orm.PromotionCode
    _ = promotions_orm.PromotionRedemption
    engine = build_engine(postgres_async_database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield build_session_factory(engine)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()

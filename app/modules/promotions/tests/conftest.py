from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from app.core.db.base import Base
from app.core.db.outbox import orm as outbox_orm
from app.core.db.session import build_engine, build_session_factory
from tests.support.database import database_url_from_postgres_container


@pytest.fixture(scope="module")
def postgres_async_database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver=None) as postgres:
        yield database_url_from_postgres_container(postgres)


@pytest.fixture
async def postgres_session_factory(
    postgres_async_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from app.modules.promotions.infrastructure.persistence import orm as promotions_orm

    _ = promotions_orm.Promotion
    _ = promotions_orm.PromotionContent
    _ = promotions_orm.PromotionCode
    _ = promotions_orm.PromotionRedemption
    _ = outbox_orm.OutboxEvent
    engine = build_engine(postgres_async_database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield build_session_factory(engine)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()

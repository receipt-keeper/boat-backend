from collections.abc import AsyncIterator, Iterator
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from app.core.db.base import Base
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.outbox.serialization import EventTypeRegistry, deserialize_event
from app.core.db.session import build_engine, build_session_factory
from app.modules.notifications.domain.events import NotificationCreated
from app.modules.notifications.domain.value_objects import NotificationMessageType
from tests.support.database import database_url_from_postgres_container


@pytest.fixture(scope="module")
def postgres_async_database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver=None) as postgres:
        yield database_url_from_postgres_container(postgres)


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


def _registry() -> EventTypeRegistry:
    registry = EventTypeRegistry()
    registry.register(NotificationCreated)
    return registry


def _sample_event() -> NotificationCreated:
    return NotificationCreated(
        notification_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        message_type=NotificationMessageType.TRANSACTIONAL,
        kind="warranty_notice",
        title="보증 기간 안내",
        message="영수증 보증 기간이 곧 만료됩니다.",
        resource_type="receipt",
        resource_id=UUID("00000000-0000-0000-0000-000000000003"),
    )


async def test_publish_then_commit_persists_outbox_row_with_matching_payload(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: outbox event publisher가 세션에 주입되어 있다.
    registry = _registry()
    event = _sample_event()

    # When: publish 후 같은 세션을 commit한다.
    async with postgres_session_factory() as session:
        publisher = OutboxEventPublisher(session=session, registry=registry)
        await publisher.publish([event])
        await session.commit()

    # Then: 별도 세션에서 조회해도 outbox row가 존재하고 payload가 원본과 일치한다.
    async with postgres_session_factory() as session:
        rows = list(await session.scalars(select(OutboxEvent)))

    assert len(rows) == 1
    row = rows[0]
    assert row.event_id == event.event_id
    assert row.event_type == "NotificationCreated"
    restored = deserialize_event(registry, row.event_type, row.payload)
    assert restored == event


async def test_publish_without_commit_then_rollback_leaves_no_outbox_row(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: outbox event publisher가 세션에 주입되어 있다.
    registry = _registry()
    event = _sample_event()

    # When: publish 후 commit 없이 rollback한다.
    async with postgres_session_factory() as session:
        publisher = OutboxEventPublisher(session=session, registry=registry)
        await publisher.publish([event])
        await session.rollback()

    # Then: outbox row는 존재하지 않는다.
    async with postgres_session_factory() as session:
        rows = list(await session.scalars(select(OutboxEvent)))

    assert rows == []

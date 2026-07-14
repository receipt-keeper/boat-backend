from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from app.core.application.event_dispatcher import EventDispatcher
from app.core.db.base import Base
from app.core.db.outbox.immediate_dispatch import (
    dispatch_outbox_event_immediately,
    dispatch_outbox_events_immediately,
)
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.outbox.serialization import EventTypeRegistry
from app.core.db.session import build_engine, build_session_factory
from app.core.domain.events import DomainEvent
from tests.support.database import database_url_from_postgres_container


class HandlerFailure(Exception):
    pass


@pytest.fixture(scope="module")
def postgres_async_database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver=None) as postgres:
        yield database_url_from_postgres_container(postgres)


@pytest.fixture
async def session_factory(
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
    registry.register(DomainEvent)
    return registry


async def _insert_committed_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    registry: EventTypeRegistry,
) -> DomainEvent:
    event = DomainEvent()
    async with session_factory() as session:
        publisher = OutboxEventPublisher(session=session, registry=registry)
        await publisher.publish([event])
        await session.commit()
    return event


async def test_dispatch_immediately_deletes_row_on_success(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = _registry()
    event = await _insert_committed_event(session_factory, registry=registry)
    dispatched: list[DomainEvent] = []

    async def handle_event(dispatched_event: DomainEvent) -> None:
        dispatched.append(dispatched_event)

    dispatcher = EventDispatcher()
    dispatcher.register(DomainEvent, handle_event)

    async with session_factory() as session:
        await dispatch_outbox_event_immediately(
            session,
            event_id=event.event_id,
            registry=registry,
            dispatcher=dispatcher,
        )

    assert len(dispatched) == 1
    async with session_factory() as session:
        rows = list(await session.scalars(select(OutboxEvent)))
    assert rows == []


async def test_dispatch_immediately_restores_row_when_handler_fails(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = _registry()
    event = await _insert_committed_event(session_factory, registry=registry)

    async def fail_handler(_event: DomainEvent) -> None:
        raise HandlerFailure

    dispatcher = EventDispatcher()
    dispatcher.register(DomainEvent, fail_handler)

    async with session_factory() as session:
        await dispatch_outbox_event_immediately(
            session,
            event_id=event.event_id,
            registry=registry,
            dispatcher=dispatcher,
        )

    # Then: 발행 실패 시 row는 삭제되지 않고 잔존한다(rollback으로 복원) - 폴러의 재시도 대상.
    async with session_factory() as session:
        rows = list(await session.scalars(select(OutboxEvent)))
    assert len(rows) == 1
    assert rows[0].event_id == event.event_id
    assert rows[0].retry_count == 0


async def test_dispatch_immediately_skips_when_row_already_gone(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = _registry()
    dispatched: list[DomainEvent] = []

    async def handle_event(dispatched_event: DomainEvent) -> None:
        dispatched.append(dispatched_event)

    dispatcher = EventDispatcher()
    dispatcher.register(DomainEvent, handle_event)

    missing_event_id: UUID = uuid4()

    # Given/When: 원 요청의 커밋이 실패해 애초에 row가 존재하지 않는 상황을 시뮬레이션한다.
    async with session_factory() as session:
        await dispatch_outbox_event_immediately(
            session,
            event_id=missing_event_id,
            registry=registry,
            dispatcher=dispatcher,
        )

    # Then: 유령 발행 없이 조용히 skip한다.
    assert dispatched == []


async def test_dispatch_events_immediately_processes_each_event_id_in_its_own_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = _registry()
    first_event = await _insert_committed_event(session_factory, registry=registry)
    second_event = await _insert_committed_event(session_factory, registry=registry)
    dispatched: list[DomainEvent] = []

    async def handle_event(dispatched_event: DomainEvent) -> None:
        dispatched.append(dispatched_event)

    dispatcher = EventDispatcher()
    dispatcher.register(DomainEvent, handle_event)

    await dispatch_outbox_events_immediately(
        session_factory,
        event_ids=[first_event.event_id, second_event.event_id],
        registry=registry,
        dispatcher=dispatcher,
    )

    assert len(dispatched) == 2
    async with session_factory() as session:
        rows = list(await session.scalars(select(OutboxEvent)))
    assert rows == []

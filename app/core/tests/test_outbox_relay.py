import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from app.core.application.event_dispatcher import EventDispatcher
from app.core.db.base import Base
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.relay import OutboxRelay
from app.core.db.outbox.serialization import EventTypeRegistry, serialize_event
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


async def _insert_event(
    session: AsyncSession,
    *,
    occurred_at: datetime,
    retry_count: int = 0,
) -> OutboxEvent:
    event = DomainEvent(occurred_at=occurred_at)
    event_type, payload = serialize_event(event)
    row = OutboxEvent(
        event_id=event.event_id,
        event_type=event_type,
        payload=payload,
        occurred_at=event.occurred_at,
        retry_count=retry_count,
    )
    session.add(row)
    await session.commit()
    return row


def _stale_timestamp(redeliver_after_seconds: int) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=redeliver_after_seconds + 1)


async def test_run_once_deletes_row_on_dispatch_success(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dispatched: list[DomainEvent] = []

    async with session_factory() as session:

        async def handle_event(event: DomainEvent) -> None:
            assert session.in_transaction() is False
            dispatched.append(event)

        dispatcher = EventDispatcher()
        dispatcher.register(DomainEvent, handle_event)
        relay = OutboxRelay(
            registry=_registry(),
            dispatcher=dispatcher,
            redeliver_after_seconds=30,
            max_retry=10,
            batch_size=100,
        )
        await _insert_event(session, occurred_at=_stale_timestamp(30))

        processed = await relay.run_once(session)

        assert processed == 1
        assert len(dispatched) == 1
        remaining = (await session.execute(select(OutboxEvent))).scalars().all()
        assert remaining == []


async def test_run_once_keeps_row_and_bumps_retry_count_on_handler_failure(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def fail_handler(_event: DomainEvent) -> None:
        raise HandlerFailure

    dispatcher = EventDispatcher()
    dispatcher.register(DomainEvent, fail_handler)
    relay = OutboxRelay(
        registry=_registry(),
        dispatcher=dispatcher,
        redeliver_after_seconds=30,
        max_retry=10,
        batch_size=100,
    )

    async with session_factory() as session:
        inserted = await _insert_event(session, occurred_at=_stale_timestamp(30))

        processed = await relay.run_once(session)
        processed_again = await relay.run_once(session)

        assert processed == 1
        assert processed_again == 0
        remaining = (await session.execute(select(OutboxEvent))).scalars().all()
        assert len(remaining) == 1
        assert remaining[0].id == inserted.id
        assert remaining[0].retry_count == 1


async def test_run_once_skips_row_within_redeliver_after_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dispatched: list[DomainEvent] = []

    async def handle_event(event: DomainEvent) -> None:
        dispatched.append(event)

    dispatcher = EventDispatcher()
    dispatcher.register(DomainEvent, handle_event)
    relay = OutboxRelay(
        registry=_registry(),
        dispatcher=dispatcher,
        redeliver_after_seconds=30,
        max_retry=10,
        batch_size=100,
    )

    async with session_factory() as session:
        # occurred_at이 방금이라 redeliver_after_seconds(30초)를 넘지 않았다.
        await _insert_event(session, occurred_at=datetime.now(UTC))

        processed = await relay.run_once(session)

        assert processed == 0
        assert dispatched == []
        remaining = (await session.execute(select(OutboxEvent))).scalars().all()
        assert len(remaining) == 1


async def test_run_once_skips_row_at_max_retry(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dispatched: list[DomainEvent] = []

    async def handle_event(event: DomainEvent) -> None:
        dispatched.append(event)

    dispatcher = EventDispatcher()
    dispatcher.register(DomainEvent, handle_event)
    relay = OutboxRelay(
        registry=_registry(),
        dispatcher=dispatcher,
        redeliver_after_seconds=30,
        max_retry=3,
        batch_size=100,
    )

    async with session_factory() as session:
        await _insert_event(session, occurred_at=_stale_timestamp(30), retry_count=3)

        processed = await relay.run_once(session)

        assert processed == 0
        assert dispatched == []
        remaining = (await session.execute(select(OutboxEvent))).scalars().all()
        assert len(remaining) == 1
        assert remaining[0].retry_count == 3


async def test_concurrent_run_once_does_not_dispatch_same_row_twice(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dispatched_a: list[DomainEvent] = []
    dispatched_b: list[DomainEvent] = []
    barrier = asyncio.Event()
    relay_b_finished = asyncio.Event()

    async def handle_event_a(event: DomainEvent) -> None:
        dispatched_a.append(event)
        barrier.set()
        await relay_b_finished.wait()

    async def handle_event_b(event: DomainEvent) -> None:
        dispatched_b.append(event)

    dispatcher_a = EventDispatcher()
    dispatcher_a.register(DomainEvent, handle_event_a)
    relay_a = OutboxRelay(
        registry=_registry(),
        dispatcher=dispatcher_a,
        redeliver_after_seconds=30,
        max_retry=10,
        batch_size=100,
    )

    dispatcher_b = EventDispatcher()
    dispatcher_b.register(DomainEvent, handle_event_b)
    relay_b = OutboxRelay(
        registry=_registry(),
        dispatcher=dispatcher_b,
        redeliver_after_seconds=30,
        max_retry=10,
        batch_size=100,
    )

    async with session_factory() as setup_session:
        await _insert_event(setup_session, occurred_at=_stale_timestamp(30))

    async def run_a() -> int:
        async with session_factory() as session:
            return await relay_a.run_once(session)

    async def run_b() -> int:
        await barrier.wait()
        try:
            async with session_factory() as session:
                return await relay_b.run_once(session)
        finally:
            relay_b_finished.set()

    processed_a, processed_b = await asyncio.gather(run_a(), run_b())

    assert processed_a + processed_b == 1
    assert len(dispatched_a) + len(dispatched_b) == 1


async def test_run_forever_stops_gracefully_on_cancellation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dispatcher = EventDispatcher()
    relay = OutboxRelay(
        registry=_registry(),
        dispatcher=dispatcher,
        redeliver_after_seconds=30,
        max_retry=10,
        batch_size=100,
    )

    task = asyncio.create_task(relay.run_forever(session_factory, interval_seconds=0.05))
    await asyncio.sleep(0.1)
    task.cancel()
    await task

    assert task.cancelled() is False

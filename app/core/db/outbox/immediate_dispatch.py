import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.application.event_dispatcher import EventDispatcher
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.serialization import EventTypeRegistry, deserialize_event

logger = logging.getLogger(__name__)


async def dispatch_outbox_event_immediately(
    session: AsyncSession,
    *,
    event_id: UUID,
    registry: EventTypeRegistry,
    dispatcher: EventDispatcher,
) -> None:
    """응답 반환 이후 새 세션에서 outbox row 1건을 claim-then-dispatch한다.

    retry_count와 occurred_at을 갱신해 row를 짧게 claim하고 즉시 commit한다.
    이후 DB 트랜잭션 없이 dispatch하며, 성공한 claim만 조건부 삭제한다.
    실패하거나 프로세스가 중단되면 row가 남아 폴러의 재시도 대상이 된다.
    """
    statement = (
        update(OutboxEvent)
        .where(OutboxEvent.event_id == event_id)
        .values(
            retry_count=OutboxEvent.retry_count + 1,
            occurred_at=datetime.now(UTC),
        )
        .returning(OutboxEvent)
    )
    result = await session.execute(statement)
    row = result.scalar_one_or_none()
    if row is None:
        # 원 요청의 커밋이 실패했거나 폴러가 이미 처리한 row다 - 유령 발행 방지를 위해 skip한다.
        await session.commit()
        return

    event_type = row.event_type
    payload = row.payload
    claimed_retry_count = row.retry_count
    await session.commit()

    try:
        event = deserialize_event(registry, event_type, payload)
        await dispatcher.dispatch([event])
    except Exception:
        logger.warning(
            "outbox 이벤트 즉시 발행에 실패했습니다. 폴러 재시도 대상으로 남깁니다. "
            "event_id=%s event_type=%s retry_count=%d",
            event_id,
            event_type,
            claimed_retry_count,
            exc_info=True,
        )
        return

    # claim 이후 다른 worker가 같은 row를 다시 claim했다면 해당 worker의 처리 결과를
    # 지우지 않도록 retry_count까지 비교한다.
    await session.execute(
        delete(OutboxEvent).where(
            OutboxEvent.event_id == event_id,
            OutboxEvent.retry_count == claimed_retry_count,
        )
    )
    await session.commit()


async def dispatch_outbox_events_immediately(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    event_ids: list[UUID],
    registry: EventTypeRegistry,
    dispatcher: EventDispatcher,
) -> None:
    """`event_ids` 각각에 대해 새 세션으로 delete-then-dispatch를 수행한다."""
    for event_id in event_ids:
        async with session_factory() as session:
            await dispatch_outbox_event_immediately(
                session,
                event_id=event_id,
                registry=registry,
                dispatcher=dispatcher,
            )

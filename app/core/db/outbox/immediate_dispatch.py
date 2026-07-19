import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
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

    원 이벤트의 occurred_at을 claim generation으로 갱신해 짧게 claim하고 즉시
    commit한다. 이후 DB 트랜잭션 없이 dispatch하며, 성공한 claim만 조건부
    삭제한다. 실패하거나 프로세스가 중단되면 row가 남아 폴러의 재시도
    대상이 된다.
    """
    statement = select(OutboxEvent).where(OutboxEvent.event_id == event_id).with_for_update()
    result = await session.execute(statement)
    row = result.scalar_one_or_none()
    if row is None:
        # 원 요청의 커밋이 실패했거나 폴러가 이미 처리한 row다 - 유령 발행 방지를 위해 skip한다.
        await session.commit()
        return

    event_type = row.event_type
    payload = row.payload
    try:
        event = deserialize_event(registry, event_type, payload)
    except Exception:
        await session.rollback()
        logger.warning(
            "outbox 이벤트 즉시 발행 역직렬화에 실패했습니다. event_id=%s event_type=%s",
            event_id,
            event_type,
            exc_info=True,
        )
        return

    # relay가 먼저 claim했거나 이미 한 번 실패한 row는 immediate 경로가 다시
    # claim하지 않는다. 원 이벤트의 occurred_at은 payload 안에 보존돼 있다.
    if row.retry_count != 0 or row.occurred_at != event.occurred_at:
        await session.commit()
        return

    claimed_at = max(
        datetime.now(UTC),
        row.occurred_at + timedelta(microseconds=1),
    )
    row.occurred_at = claimed_at
    await session.commit()

    try:
        await dispatcher.dispatch([event])
    except Exception:
        await session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.event_id == event_id,
                OutboxEvent.retry_count == 0,
                OutboxEvent.occurred_at == claimed_at,
            )
            .values(retry_count=1)
        )
        await session.commit()
        logger.warning(
            "outbox 이벤트 즉시 발행에 실패했습니다. 폴러 재시도 대상으로 남깁니다. "
            "event_id=%s event_type=%s retry_count=1",
            event_id,
            event_type,
            exc_info=True,
        )
        return

    # claim 이후 다른 worker가 lease 만료 row를 다시 claim했다면 해당 worker의
    # 처리 결과를 지우지 않도록 claim 시각까지 비교한다.
    await session.execute(
        delete(OutboxEvent).where(
            OutboxEvent.event_id == event_id,
            OutboxEvent.retry_count == 0,
            OutboxEvent.occurred_at == claimed_at,
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

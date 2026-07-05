import logging
from uuid import UUID

from sqlalchemy import delete
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
    """응답 반환 이후 새 세션에서 outbox row 1건을 delete-then-dispatch한다.

    row를 먼저 DELETE ... RETURNING으로 회수해 rowcount가 0이면(원 커밋 실패로
    row가 애초에 없거나 폴러가 이미 처리한 경우) 아무 것도 하지 않고 조용히
    반환한다. row를 회수했다면 역직렬화 후 dispatch하고, 성공 시 commit해
    row 삭제를 확정하며, 실패 시 rollback으로 row를 복원해 폴러의 재시도
    대상으로 남긴다.
    """
    statement = delete(OutboxEvent).where(OutboxEvent.event_id == event_id).returning(OutboxEvent)
    result = await session.execute(statement)
    row = result.scalar_one_or_none()
    if row is None:
        # 원 요청의 커밋이 실패했거나 폴러가 이미 처리한 row다 - 유령 발행 방지를 위해 skip한다.
        return

    event_type = row.event_type
    try:
        event = deserialize_event(registry, event_type, row.payload)
        await dispatcher.dispatch([event])
    except Exception:
        # rollback은 세션의 row 객체를 expire시키므로, 로그에 쓸 값은 rollback 전에
        # 미리 캡처해 둔다(rollback 이후 attribute 접근은 추가 IO를 유발해 실패한다).
        await session.rollback()
        logger.warning(
            "outbox 이벤트 즉시 발행에 실패했습니다. 폴러 재시도 대상으로 남깁니다. "
            "event_id=%s event_type=%s",
            event_id,
            event_type,
            exc_info=True,
        )
        return

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

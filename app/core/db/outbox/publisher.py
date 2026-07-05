from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.event_publisher import EventPublisher
from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.serialization import EventTypeRegistry, serialize_event
from app.core.domain.events import DomainEvent


class OutboxEventPublisher(EventPublisher):
    """이벤트를 직렬화해 같은 세션에 outbox row로 insert만 하는 발행자.

    `publish()`는 커밋을 수행하지 않는다 — 세션 라이프사이클(commit/rollback)은
    호출자(use case가 소유한 UnitOfWork)의 책임이며, 이 발행자가 insert한 row는
    호출자의 트랜잭션과 같은 원자적 단위로 커밋되거나 함께 롤백된다.
    """

    def __init__(self, *, session: AsyncSession, registry: EventTypeRegistry) -> None:
        self._session = session
        self._registry = registry

    async def publish(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            event_type, payload = serialize_event(event)
            # 등록되지 않은 이벤트 타입은 이후 역직렬화(즉시 발행/폴러)에서 복원할 수
            # 없으므로, insert 이전에 명시적으로 실패시켜 유실을 방지한다.
            self._registry.resolve(event_type)
            self._session.add(
                OutboxEvent(
                    event_id=event.event_id,
                    event_type=event_type,
                    payload=payload,
                    occurred_at=event.occurred_at,
                )
            )

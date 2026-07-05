from collections.abc import Sequence
from typing import Protocol

from app.core.domain.events import DomainEvent


class EventPublisher(Protocol):
    async def publish(self, events: Sequence[DomainEvent]) -> None: ...


class NoOpEventPublisher(EventPublisher):
    """이벤트를 발행하지 않는 EventPublisher 구현.

    표준 발행 경로(예: background 푸시 디스패치)를 우회해야 하는 보조 조립
    지점에서 사용한다. `DeferredCommitUnitOfWork`와 같은 층에 두는 port-owned
    no-op이다.
    """

    async def publish(self, events: Sequence[DomainEvent]) -> None:
        return None

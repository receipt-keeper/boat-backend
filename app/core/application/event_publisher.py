from collections.abc import Sequence
from typing import Protocol

from app.core.domain.events import DomainEvent


class EventPublisher(Protocol):
    async def publish(self, events: Sequence[DomainEvent]) -> None: ...

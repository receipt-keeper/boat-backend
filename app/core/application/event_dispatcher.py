from collections.abc import Awaitable, Callable, Sequence

from app.core.domain.events import DomainEvent

type EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventDispatcher:
    """Same-process application event dispatcher.

    This dispatcher has no outbox, retry, replay, broker, or cross-process delivery contract.
    Handler failures are propagated to the caller.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = {}

    def register(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            for handler in self._handlers.get(type(event), []):
                await handler(event)

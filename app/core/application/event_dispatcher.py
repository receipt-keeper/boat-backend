from collections.abc import Awaitable, Callable, Sequence

from app.core.domain.events import DomainEvent

type EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventDispatcher:
    """Same-process application event dispatcher.

    This dispatcher itself still has no outbox, retry, replay, broker, or
    cross-process delivery contract - it only invokes registered handlers
    in-process and propagates handler failures to the caller. Outbox
    persistence and retry are a separate concern owned by `app.core.db.outbox`
    (`OutboxEventPublisher`, `OutboxRelay`), which call into this dispatcher
    rather than replacing it.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = {}

    def register(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            for handler in self._handlers.get(type(event), []):
                await handler(event)

import pytest

from app.core.application.event_dispatcher import EventDispatcher
from app.core.domain.events import DomainEvent


class HandlerFailure(Exception):
    pass


async def test_dispatch_calls_registered_handler() -> None:
    dispatcher = EventDispatcher()
    event = DomainEvent()
    handled_events: list[DomainEvent] = []

    async def handle_event(handled_event: DomainEvent) -> None:
        handled_events.append(handled_event)

    dispatcher.register(DomainEvent, handle_event)

    await dispatcher.dispatch([event])

    assert handled_events == [event]


async def test_dispatch_ignores_unregistered_event() -> None:
    dispatcher = EventDispatcher()

    await dispatcher.dispatch([DomainEvent()])


async def test_dispatch_propagates_handler_failure() -> None:
    dispatcher = EventDispatcher()

    async def fail_handler(_event: DomainEvent) -> None:
        raise HandlerFailure

    dispatcher.register(DomainEvent, fail_handler)

    with pytest.raises(HandlerFailure):
        await dispatcher.dispatch([DomainEvent()])

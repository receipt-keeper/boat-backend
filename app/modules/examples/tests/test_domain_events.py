from collections.abc import Sequence

import pytest

from app.core.application.event_dispatcher import EventDispatcher
from app.core.domain.events import DomainEvent
from app.core.domain.exceptions import ValidationError
from app.modules.examples.application.service import ExampleUserService
from app.modules.examples.domain.events import ExampleUserCreated
from app.modules.examples.domain.model import ExampleUser
from app.modules.examples.infrastructure.repository import ExampleUserRepository


class RecordingEventDispatcher(EventDispatcher):
    def __init__(self) -> None:
        super().__init__()
        self.dispatched_events: list[DomainEvent] = []

    async def dispatch(self, events: Sequence[DomainEvent]) -> None:
        self.dispatched_events.extend(events)
        await super().dispatch(events)


def test_example_user_create_records_created_event() -> None:
    example_user = ExampleUser.create(
        nickname="created-user",
        email="created@test.com",
        password="password123",
    )

    events = example_user.pull_events()

    assert events == [
        ExampleUserCreated(
            example_user_id=example_user.id,
            email="created@test.com",
            event_id=events[0].event_id,
            occurred_at=events[0].occurred_at,
        )
    ]


def test_example_user_create_does_not_record_event_on_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_events: list[DomainEvent] = []
    original_record_event = ExampleUser.record_event

    def record_event_spy(example_user: ExampleUser, event: DomainEvent) -> None:
        recorded_events.append(event)
        original_record_event(example_user, event)

    monkeypatch.setattr(ExampleUser, "record_event", record_event_spy)

    with pytest.raises(ValidationError):
        ExampleUser.create(nickname="", email="invalid", password="short")

    assert recorded_events == []


async def test_example_user_service_dispatches_events_after_save() -> None:
    dispatcher = RecordingEventDispatcher()
    service = ExampleUserService(ExampleUserRepository(), dispatcher)

    example_user = await service.create_example_user(
        nickname="created-user",
        email="created@test.com",
        password="password123",
    )

    assert dispatcher.dispatched_events == [
        ExampleUserCreated(
            example_user_id=example_user.id,
            email="created@test.com",
            event_id=dispatcher.dispatched_events[0].event_id,
            occurred_at=dispatcher.dispatched_events[0].occurred_at,
        )
    ]
    assert example_user.pull_events() == []

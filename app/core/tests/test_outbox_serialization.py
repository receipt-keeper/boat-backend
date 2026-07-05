from uuid import UUID

import pytest

from app.core.db.outbox.serialization import (
    EventTypeRegistry,
    UnregisteredEventTypeError,
    deserialize_event,
    serialize_event,
)
from app.modules.notifications.domain.events import NotificationCreated
from app.modules.notifications.domain.value_objects import NotificationMessageType


def _sample_event() -> NotificationCreated:
    return NotificationCreated(
        notification_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        message_type=NotificationMessageType.TRANSACTIONAL,
        kind="warranty_notice",
        title="보증 기간 안내",
        message="영수증 보증 기간이 곧 만료됩니다.",
        resource_type="receipt",
        resource_id=UUID("00000000-0000-0000-0000-000000000003"),
    )


def _registry() -> EventTypeRegistry:
    registry = EventTypeRegistry()
    registry.register(NotificationCreated)
    return registry


def test_serialize_and_deserialize_round_trips_all_fields() -> None:
    registry = _registry()
    event = _sample_event()

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event


def test_serialize_and_deserialize_round_trips_none_resource_fields() -> None:
    registry = _registry()
    event = NotificationCreated(
        notification_id=UUID("00000000-0000-0000-0000-000000000004"),
        user_id=UUID("00000000-0000-0000-0000-000000000005"),
        message_type=NotificationMessageType.MARKETING,
        kind="benefit",
        title="혜택 안내",
        message="새로운 혜택이 도착했습니다.",
        resource_type=None,
        resource_id=None,
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, NotificationCreated)
    assert restored.resource_type is None
    assert restored.resource_id is None


def test_serialize_preserves_base_domain_event_fields() -> None:
    registry = _registry()
    event = _sample_event()

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored.event_id == event.event_id
    assert restored.occurred_at == event.occurred_at
    assert restored.event_version == event.event_version


def test_deserialize_restores_str_enum_member_not_plain_string() -> None:
    registry = _registry()
    event = _sample_event()

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert isinstance(restored, NotificationCreated)
    assert isinstance(restored.message_type, NotificationMessageType)
    assert restored.message_type is NotificationMessageType.TRANSACTIONAL


def test_serialize_uses_class_name_as_event_type() -> None:
    event_type, _payload = serialize_event(_sample_event())

    assert event_type == "NotificationCreated"


def test_deserialize_unregistered_event_type_raises_explicit_error() -> None:
    registry = EventTypeRegistry()

    with pytest.raises(UnregisteredEventTypeError):
        deserialize_event(registry, "NotificationCreated", {})


def test_registry_lookup_of_unregistered_type_raises_explicit_error() -> None:
    registry = EventTypeRegistry()

    with pytest.raises(UnregisteredEventTypeError):
        registry.resolve("SomethingNotRegistered")

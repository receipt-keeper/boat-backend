from dataclasses import dataclass
from uuid import UUID

import pytest

from app.core.db.outbox.serialization import (
    EventTypeRegistry,
    UnregisteredEventTypeError,
    deserialize_event,
    serialize_event,
)
from app.core.domain.events import DomainEvent
from app.modules.notifications.domain.events import NotificationCreated
from app.modules.notifications.domain.value_objects import NotificationMessageType


@dataclass(frozen=True, kw_only=True)
class _OtherModuleEvent(DomainEvent):
    """다른 모듈의 registry를 흉내 낸 테스트 전용 이벤트 타입."""

    payload_id: UUID


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


def test_merge_absorbs_other_registrys_types_and_resolves_both() -> None:
    """두 모듈 registry를 병합하면 양쪽 이벤트 타입 모두 resolve된다 (main.py 병합 지점 계약)."""
    notifications_registry = _registry()
    other_module_registry = EventTypeRegistry()
    other_module_registry.register(_OtherModuleEvent)

    merged = EventTypeRegistry()
    merged.merge(notifications_registry)
    merged.merge(other_module_registry)

    assert merged.resolve("NotificationCreated") is NotificationCreated
    assert merged.resolve("_OtherModuleEvent") is _OtherModuleEvent


def test_merge_does_not_mutate_the_registry_being_merged_in() -> None:
    source = EventTypeRegistry()
    source.register(_OtherModuleEvent)

    merged = EventTypeRegistry()
    merged.merge(source)
    merged.register(NotificationCreated)

    with pytest.raises(UnregisteredEventTypeError):
        source.resolve("NotificationCreated")


def test_merge_still_raises_for_types_registered_in_neither_source() -> None:
    merged = EventTypeRegistry()
    merged.merge(_registry())

    with pytest.raises(UnregisteredEventTypeError):
        merged.resolve("SomethingNeverRegisteredAnywhere")

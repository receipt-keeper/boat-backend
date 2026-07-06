from uuid import UUID

from app.core.db.outbox.serialization import EventTypeRegistry, deserialize_event, serialize_event
from app.modules.users.domain.events import (
    UserProfileImageChanged,
    UserRegistered,
    UserWithdrawn,
)


def _registry() -> EventTypeRegistry:
    registry = EventTypeRegistry()
    registry.register(UserRegistered)
    registry.register(UserProfileImageChanged)
    registry.register(UserWithdrawn)
    return registry


def test_user_registered_round_trips_all_fields() -> None:
    registry = _registry()
    event = UserRegistered(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        email="person@example.com",
        name="테스트 사용자",
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert event_type == "UserRegistered"


def test_user_registered_round_trips_none_email_and_name() -> None:
    registry = _registry()
    event = UserRegistered(
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        email=None,
        name=None,
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, UserRegistered)
    assert restored.email is None
    assert restored.name is None


def test_user_profile_image_changed_round_trips_all_fields() -> None:
    registry = _registry()
    event = UserProfileImageChanged(
        user_id=UUID("00000000-0000-0000-0000-000000000003"),
        previous_image_url="/files/old/content",
        new_image_url="/files/new/content",
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert event_type == "UserProfileImageChanged"


def test_user_profile_image_changed_round_trips_cleared_image() -> None:
    registry = _registry()
    event = UserProfileImageChanged(
        user_id=UUID("00000000-0000-0000-0000-000000000004"),
        previous_image_url="/files/old/content",
        new_image_url=None,
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, UserProfileImageChanged)
    assert restored.new_image_url is None


def test_user_withdrawn_round_trips() -> None:
    registry = _registry()
    event = UserWithdrawn(user_id=UUID("00000000-0000-0000-0000-000000000005"))

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert event_type == "UserWithdrawn"


def test_users_event_registry_builder_registers_all_three_event_types() -> None:
    from app.modules.users.dependencies import build_users_event_registry

    registry = build_users_event_registry()

    assert registry.resolve("UserRegistered") is UserRegistered
    assert registry.resolve("UserProfileImageChanged") is UserProfileImageChanged
    assert registry.resolve("UserWithdrawn") is UserWithdrawn

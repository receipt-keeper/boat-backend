from uuid import UUID

from app.core.db.outbox.serialization import EventTypeRegistry, deserialize_event, serialize_event
from app.modules.auth.domain.events import AccountWithdrawn, UserCredentialCreated


def _registry() -> EventTypeRegistry:
    registry = EventTypeRegistry()
    registry.register(UserCredentialCreated)
    registry.register(AccountWithdrawn)
    return registry


def test_user_credential_created_round_trips_all_fields() -> None:
    registry = _registry()
    event = UserCredentialCreated(
        credentials_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        role="user",
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert event_type == "UserCredentialCreated"


def test_user_credential_created_round_trips_admin_role() -> None:
    registry = _registry()
    event = UserCredentialCreated(
        credentials_id=UUID("00000000-0000-0000-0000-000000000003"),
        user_id=UUID("00000000-0000-0000-0000-000000000004"),
        role="admin",
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, UserCredentialCreated)
    assert restored.role == "admin"


def test_account_withdrawn_round_trips() -> None:
    registry = _registry()
    event = AccountWithdrawn(
        credentials_id=UUID("00000000-0000-0000-0000-000000000005"),
        user_id=UUID("00000000-0000-0000-0000-000000000006"),
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert event_type == "AccountWithdrawn"


def test_auth_event_registry_builder_registers_both_event_types() -> None:
    from app.modules.auth.dependencies import build_auth_event_registry

    registry = build_auth_event_registry()

    assert registry.resolve("UserCredentialCreated") is UserCredentialCreated
    assert registry.resolve("AccountWithdrawn") is AccountWithdrawn

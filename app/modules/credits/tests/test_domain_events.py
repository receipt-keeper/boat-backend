from uuid import UUID

from app.core.db.outbox.serialization import deserialize_event, serialize_event
from app.modules.credits.dependencies import build_credits_event_registry
from app.modules.credits.domain import CreditReason, CreditSourceType
from app.modules.credits.domain.events import CreditGranted, CreditUsed, UserCreditsDeleted

USER_ID = UUID("00000000-0000-0000-0000-000000000101")
SOURCE_ID = UUID("00000000-0000-0000-0000-000000000901")


def test_credit_granted_serialization_round_trips_all_fields() -> None:
    registry = build_credits_event_registry()
    event = CreditGranted(
        user_id=USER_ID,
        amount=5,
        reason=CreditReason.EVENT_OCR_ALLOWANCE,
        source_type=CreditSourceType.PROMOTION_REDEMPTION,
        source_id=SOURCE_ID,
        idempotency_key="promotionRedemption:source:user",
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, CreditGranted)
    assert isinstance(restored.reason, CreditReason)
    assert isinstance(restored.source_type, CreditSourceType)


def test_credit_granted_serialization_round_trips_none_source_fields() -> None:
    registry = build_credits_event_registry()
    event = CreditGranted(
        user_id=USER_ID,
        amount=5,
        reason=CreditReason.MONTHLY_OCR_ALLOWANCE,
        source_type=None,
        source_id=None,
        idempotency_key=None,
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, CreditGranted)
    assert restored.source_type is None
    assert restored.source_id is None
    assert restored.idempotency_key is None


def test_credit_used_serialization_round_trips_all_fields() -> None:
    registry = build_credits_event_registry()
    event = CreditUsed(
        user_id=USER_ID,
        amount=1,
        reason=CreditReason.OCR_USAGE,
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, CreditUsed)
    assert isinstance(restored.reason, CreditReason)


def test_user_credits_deleted_serialization_round_trips_all_fields() -> None:
    registry = build_credits_event_registry()
    event = UserCreditsDeleted(user_id=USER_ID)

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, UserCreditsDeleted)


def test_build_credits_event_registry_resolves_all_three_event_types() -> None:
    registry = build_credits_event_registry()

    assert registry.resolve("CreditGranted") is CreditGranted
    assert registry.resolve("CreditUsed") is CreditUsed
    assert registry.resolve("UserCreditsDeleted") is UserCreditsDeleted

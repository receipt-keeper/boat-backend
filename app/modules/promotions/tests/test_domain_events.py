from uuid import UUID

from app.core.db.outbox.serialization import deserialize_event, serialize_event
from app.modules.promotions.dependencies import build_promotions_event_registry
from app.modules.promotions.domain.events import PromotionRedemptionGranted

REDEMPTION_ID = UUID("00000000-0000-0000-0000-000000000301")
PROMOTION_ID = UUID("00000000-0000-0000-0000-000000000201")
USER_ID = UUID("00000000-0000-0000-0000-000000000101")
CODE_ID = UUID("00000000-0000-0000-0000-000000000401")


def test_promotion_redemption_granted_serialization_round_trips_all_fields() -> None:
    registry = build_promotions_event_registry()
    event = PromotionRedemptionGranted(
        redemption_id=REDEMPTION_ID,
        promotion_id=PROMOTION_ID,
        user_id=USER_ID,
        promotion_code_id=CODE_ID,
        benefit_amount=3,
        idempotency_key=f"promotionRedemption:{PROMOTION_ID}:{USER_ID}",
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, PromotionRedemptionGranted)


def test_promotion_redemption_granted_serialization_round_trips_none_code_id() -> None:
    registry = build_promotions_event_registry()
    event = PromotionRedemptionGranted(
        redemption_id=REDEMPTION_ID,
        promotion_id=PROMOTION_ID,
        user_id=USER_ID,
        promotion_code_id=None,
        benefit_amount=5,
        idempotency_key=f"promotionRedemption:{PROMOTION_ID}:{USER_ID}",
    )

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, PromotionRedemptionGranted)
    assert restored.promotion_code_id is None
    assert restored.benefit_amount == 5


def test_build_promotions_event_registry_resolves_promotion_redemption_granted() -> None:
    registry = build_promotions_event_registry()

    assert registry.resolve("PromotionRedemptionGranted") is PromotionRedemptionGranted

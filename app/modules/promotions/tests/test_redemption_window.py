from datetime import UTC, datetime
from uuid import UUID

from app.modules.promotions.application.redemption_window import (
    current_user_redemption_window,
)
from app.modules.promotions.domain.model import (
    Promotion,
    PromotionBenefitFeatureKey,
    PromotionContext,
    PromotionKind,
)


def test_rewarded_ad_window_uses_kst_calendar_day() -> None:
    promotion = _promotion(PromotionKind.REWARDED_AD)

    window = current_user_redemption_window(
        promotion=promotion,
        at=datetime(2026, 7, 17, 14, 59, 59, tzinfo=UTC),
    )

    assert window.starts_at == datetime(2026, 7, 16, 15, 0, tzinfo=UTC)
    assert window.expires_at == datetime(2026, 7, 17, 15, 0, tzinfo=UTC)


def test_rewarded_ad_window_changes_at_kst_midnight() -> None:
    promotion = _promotion(PromotionKind.REWARDED_AD)

    window = current_user_redemption_window(
        promotion=promotion,
        at=datetime(2026, 7, 17, 15, 0, tzinfo=UTC),
    )

    assert window.starts_at == datetime(2026, 7, 17, 15, 0, tzinfo=UTC)
    assert window.expires_at == datetime(2026, 7, 18, 15, 0, tzinfo=UTC)


def test_non_rewarded_promotion_has_lifetime_window() -> None:
    promotion = _promotion(PromotionKind.MONTHLY_ALLOWANCE)

    window = current_user_redemption_window(
        promotion=promotion,
        at=datetime(2026, 7, 17, 15, 0, tzinfo=UTC),
    )

    assert window.starts_at is None
    assert window.expires_at is None


def _promotion(kind: PromotionKind) -> Promotion:
    return Promotion.restore(
        promotion_id=UUID("00000000-0000-0000-0000-000000000201"),
        name="OCR 크레딧 충전",
        active=True,
        starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        expires_at=None,
        max_redemptions=None,
        times_redeemed=0,
        max_redemptions_per_user=2,
        benefit_feature_key=PromotionBenefitFeatureKey.OCR,
        context=PromotionContext.RECHARGE,
        kind=kind,
        benefit_amount=2,
    )

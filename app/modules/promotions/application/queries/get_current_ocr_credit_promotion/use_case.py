from collections.abc import Callable
from datetime import UTC, datetime

from app.modules.promotions.application.ports.promotion_repository import PromotionRepository
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.query import (
    GetCurrentOcrCreditPromotionQuery,
)
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.result import (
    GetCurrentOcrCreditPromotionResult,
)
from app.modules.promotions.application.redemption_window import current_user_redemption_window
from app.modules.promotions.domain.model import Promotion


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GetCurrentOcrCreditPromotionQueryUseCase:
    def __init__(
        self,
        *,
        promotion_repository: PromotionRepository,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._promotion_repository = promotion_repository
        self._clock = clock

    async def execute(
        self,
        query: GetCurrentOcrCreditPromotionQuery,
    ) -> GetCurrentOcrCreditPromotionResult | None:
        now = self._clock()
        promotion = await self._promotion_repository.find_current_ocr_credit_promotion(
            at=now,
            context=query.context,
            kind=query.kind,
        )
        if promotion is None:
            return None
        promotion.ensure_redeemable(at=now)
        window = current_user_redemption_window(promotion=promotion, at=now)
        user_redemption_count = await self._promotion_repository.count_user_redemptions(
            user_id=query.user_id,
            promotion_id=promotion.id,
            redeemed_at_from=window.starts_at,
            redeemed_at_before=window.expires_at,
        )
        already_redeemed = user_redemption_count >= promotion.max_redemptions_per_user
        redemption = (
            await self._promotion_repository.find_redemption_by_user_and_promotion(
                user_id=query.user_id,
                promotion_id=promotion.id,
            )
            if already_redeemed
            else None
        )
        content = await self._promotion_repository.find_content_by_promotion_id(
            promotion_id=promotion.id,
        )
        return GetCurrentOcrCreditPromotionResult(
            promotion_id=promotion.id,
            name=promotion.name,
            kind=promotion.kind,
            benefit_amount=promotion.benefit_amount.value,
            remaining_redemptions=_remaining_redemptions(promotion),
            max_redemptions_per_user=promotion.max_redemptions_per_user,
            remaining_redemptions_for_user=max(
                promotion.max_redemptions_per_user - user_redemption_count,
                0,
            ),
            starts_at=promotion.starts_at,
            expires_at=promotion.expires_at,
            already_redeemed=already_redeemed,
            redemption_status=redemption.status if redemption is not None else None,
            banner_image_url=content.banner_image_url if content is not None else None,
        )


def _remaining_redemptions(promotion: Promotion) -> int | None:
    if promotion.max_redemptions is None:
        return None
    return max(promotion.max_redemptions - promotion.times_redeemed, 0)

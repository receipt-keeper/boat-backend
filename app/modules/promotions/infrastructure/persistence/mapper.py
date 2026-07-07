from app.modules.promotions.domain.model import (
    Promotion,
    PromotionBenefitFeatureKey,
    PromotionCode,
    PromotionContent,
    PromotionContext,
    PromotionRedemption,
    PromotionRedemptionStatus,
)
from app.modules.promotions.infrastructure.persistence import orm


def promotion_to_domain(record: orm.Promotion) -> Promotion:
    return Promotion.restore(
        promotion_id=record.id,
        name=record.name,
        active=record.active,
        starts_at=record.starts_at,
        expires_at=record.expires_at,
        max_redemptions=record.max_redemptions,
        times_redeemed=record.times_redeemed,
        max_redemptions_per_user=record.max_redemptions_per_user,
        benefit_feature_key=PromotionBenefitFeatureKey(record.benefit_feature_key),
        context=None if record.context is None else PromotionContext(record.context),
        benefit_amount=record.benefit_amount,
    )


def promotion_content_to_domain(record: orm.PromotionContent) -> PromotionContent:
    return PromotionContent(
        id=record.id,
        promotion_id=record.promotion_id,
        banner_image_url=record.banner_image_url,
    )


def promotion_code_to_domain(record: orm.PromotionCode) -> PromotionCode:
    return PromotionCode(
        id=record.id,
        promotion_id=record.promotion_id,
        code=record.code,
        active=record.active,
        starts_at=record.starts_at,
        expires_at=record.expires_at,
        max_redemptions=record.max_redemptions,
        times_redeemed=record.times_redeemed,
    )


def redemption_to_domain(record: orm.PromotionRedemption) -> PromotionRedemption:
    return PromotionRedemption.restore(
        redemption_id=record.id,
        promotion_id=record.promotion_id,
        promotion_code_id=record.promotion_code_id,
        user_id=record.user_id,
        status=PromotionRedemptionStatus(record.status),
        idempotency_key=record.idempotency_key,
        failure_reason=record.failure_reason,
        redeemed_at=record.redeemed_at,
    )


def redemption_to_record(redemption: PromotionRedemption) -> orm.PromotionRedemption:
    return orm.PromotionRedemption(
        id=redemption.id,
        promotion_id=redemption.promotion_id,
        promotion_code_id=redemption.promotion_code_id,
        user_id=redemption.user_id,
        status=redemption.status.value,
        idempotency_key=redemption.idempotency_key,
        failure_reason=redemption.failure_reason,
        redeemed_at=redemption.redeemed_at,
    )

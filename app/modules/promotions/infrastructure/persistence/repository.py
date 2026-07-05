from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.promotions.application.ports.promotion_repository import (
    PromotionRepository,
)
from app.modules.promotions.domain.model import (
    Promotion,
    PromotionBenefitFeatureKey,
    PromotionCode,
    PromotionContent,
    PromotionRedemption,
    PromotionRedemptionStatus,
)
from app.modules.promotions.infrastructure.persistence import mapper, orm


class SqlAlchemyPromotionRepository(PromotionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_current_ocr_credit_promotion(self, *, at: datetime) -> Promotion | None:
        record = await self._session.scalar(
            select(orm.Promotion)
            .where(
                orm.Promotion.active.is_(True),
                orm.Promotion.benefit_feature_key == PromotionBenefitFeatureKey.OCR.value,
                orm.Promotion.starts_at <= at,
                or_(orm.Promotion.expires_at.is_(None), orm.Promotion.expires_at > at),
                or_(
                    orm.Promotion.max_redemptions.is_(None),
                    orm.Promotion.times_redeemed < orm.Promotion.max_redemptions,
                ),
            )
            .order_by(orm.Promotion.starts_at.desc(), orm.Promotion.id.desc())
            .limit(1)
        )
        if record is None:
            return None
        return mapper.promotion_to_domain(record)

    async def find_content_by_promotion_id(self, *, promotion_id: UUID) -> PromotionContent | None:
        record = await self._session.scalar(
            select(orm.PromotionContent)
            .where(orm.PromotionContent.promotion_id == promotion_id)
            .limit(1)
        )
        if record is None:
            return None
        return mapper.promotion_content_to_domain(record)

    async def find_promotion_for_update(self, *, promotion_id: UUID) -> Promotion | None:
        record = await self._session.scalar(
            select(orm.Promotion).where(orm.Promotion.id == promotion_id).with_for_update()
        )
        if record is None:
            return None
        return mapper.promotion_to_domain(record)

    async def find_code_by_code_for_update(self, *, code: str) -> PromotionCode | None:
        record = await self._session.scalar(
            select(orm.PromotionCode)
            .where(func.lower(orm.PromotionCode.code) == code.lower())
            .with_for_update()
        )
        if record is None:
            return None
        return mapper.promotion_code_to_domain(record)

    async def find_redemption_by_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> PromotionRedemption | None:
        record = await self._session.scalar(
            select(orm.PromotionRedemption)
            .where(orm.PromotionRedemption.idempotency_key == idempotency_key)
            .limit(1)
        )
        if record is None:
            return None
        return mapper.redemption_to_domain(record)

    async def find_redemption_by_user_and_promotion(
        self,
        *,
        user_id: UUID,
        promotion_id: UUID,
    ) -> PromotionRedemption | None:
        record = await self._session.scalar(
            select(orm.PromotionRedemption)
            .where(
                orm.PromotionRedemption.user_id == user_id,
                orm.PromotionRedemption.promotion_id == promotion_id,
            )
            .limit(1)
        )
        if record is None:
            return None
        return mapper.redemption_to_domain(record)

    async def count_user_redemptions(self, *, user_id: UUID, promotion_id: UUID) -> int:
        return (
            await self._session.scalar(
                select(func.count())
                .select_from(orm.PromotionRedemption)
                .where(
                    orm.PromotionRedemption.user_id == user_id,
                    orm.PromotionRedemption.promotion_id == promotion_id,
                    orm.PromotionRedemption.status == PromotionRedemptionStatus.GRANTED.value,
                )
            )
            or 0
        )

    async def create_redemption(self, *, redemption: PromotionRedemption) -> None:
        self._session.add(mapper.redemption_to_record(redemption))
        await self._session.flush()

    async def save_promotion(self, *, promotion: Promotion) -> None:
        record = await self._session.get(orm.Promotion, promotion.id)
        if record is None:
            return
        record.times_redeemed = promotion.times_redeemed
        await self._session.flush()

    async def save_code(self, *, code: PromotionCode) -> None:
        record = await self._session.get(orm.PromotionCode, code.id)
        if record is None:
            return
        record.times_redeemed = code.times_redeemed
        await self._session.flush()

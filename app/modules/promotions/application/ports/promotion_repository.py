from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.modules.promotions.domain.model import (
    Promotion,
    PromotionBenefitFeatureKey,
    PromotionCode,
    PromotionContent,
    PromotionContext,
    PromotionRedemption,
)


class PromotionRepository(ABC):
    @abstractmethod
    async def find_current_ocr_credit_promotion(
        self,
        *,
        at: datetime,
        context: PromotionContext | None = None,
    ) -> Promotion | None:
        raise NotImplementedError

    @abstractmethod
    async def find_current_ocr_credit_promotion_for_update(
        self,
        *,
        at: datetime,
        context: PromotionContext,
    ) -> Promotion | None:
        raise NotImplementedError

    @abstractmethod
    async def find_content_by_promotion_id(self, *, promotion_id: UUID) -> PromotionContent | None:
        raise NotImplementedError

    @abstractmethod
    async def find_promotion_for_update(self, *, promotion_id: UUID) -> Promotion | None:
        raise NotImplementedError

    @abstractmethod
    async def find_promotion_by_benefit_context_start_for_update(
        self,
        *,
        benefit_feature_key: PromotionBenefitFeatureKey,
        context: PromotionContext,
        starts_at: datetime,
    ) -> Promotion | None:
        raise NotImplementedError

    @abstractmethod
    async def find_code_by_code_for_update(self, *, code: str) -> PromotionCode | None:
        raise NotImplementedError

    @abstractmethod
    async def find_redemption_by_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> PromotionRedemption | None:
        raise NotImplementedError

    @abstractmethod
    async def find_redemption_by_user_and_promotion(
        self,
        *,
        user_id: UUID,
        promotion_id: UUID,
    ) -> PromotionRedemption | None:
        raise NotImplementedError

    @abstractmethod
    async def find_redemption_by_promotion_and_beneficiary(
        self,
        *,
        promotion_id: UUID,
        beneficiary_key: str,
    ) -> PromotionRedemption | None:
        raise NotImplementedError

    @abstractmethod
    async def count_user_redemptions(
        self,
        *,
        user_id: UUID,
        promotion_id: UUID,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def create_redemption(self, *, redemption: PromotionRedemption) -> None:
        raise NotImplementedError

    @abstractmethod
    async def create_promotion(self, *, promotion: Promotion) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save_promotion(self, *, promotion: Promotion) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save_code(self, *, code: PromotionCode) -> None:
        raise NotImplementedError

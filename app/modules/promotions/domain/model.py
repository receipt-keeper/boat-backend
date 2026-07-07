from dataclasses import InitVar, dataclass
from datetime import datetime
from enum import StrEnum
from typing import assert_never
from uuid import UUID, uuid4

from app.core.domain.entity import AggregateRoot, Entity
from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.promotions.domain.events import PromotionRedemptionGranted
from app.modules.promotions.domain.exceptions import PromotionRedemptionConflictError

_POSITIVE_AMOUNT_MESSAGE = "프로모션 지급 크레딧은 1 이상이어야 합니다."


class PromotionBenefitFeatureKey(StrEnum):
    OCR = "ocr"


class PromotionContext(StrEnum):
    RECHARGE = "recharge"


class PromotionRedemptionStatus(StrEnum):
    GRANTED = "granted"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PromotionBenefitAmount:
    value: int
    field_name: InitVar[str] = "benefit_amount"

    def __post_init__(self, field_name: str) -> None:
        if self.value < 1:
            raise ValidationError([ErrorDetail(field=field_name, message=_POSITIVE_AMOUNT_MESSAGE)])


@dataclass(eq=False, slots=True)  # noqa: RUF100  # noqa: MUTABLE_OK
class Promotion(AggregateRoot[UUID]):
    name: str
    active: bool
    starts_at: datetime
    expires_at: datetime | None
    max_redemptions: int | None
    times_redeemed: int
    max_redemptions_per_user: int
    benefit_feature_key: PromotionBenefitFeatureKey
    context: PromotionContext | None
    benefit_amount: PromotionBenefitAmount

    @classmethod
    def restore(
        cls,
        *,
        promotion_id: UUID,
        name: str,
        active: bool,
        starts_at: datetime,
        expires_at: datetime | None,
        max_redemptions: int | None,
        times_redeemed: int,
        max_redemptions_per_user: int,
        benefit_feature_key: PromotionBenefitFeatureKey,
        context: PromotionContext | None = None,
        benefit_amount: int | PromotionBenefitAmount,
    ) -> "Promotion":
        return cls(
            id=promotion_id,
            name=name,
            active=active,
            starts_at=starts_at,
            expires_at=expires_at,
            max_redemptions=max_redemptions,
            times_redeemed=times_redeemed,
            max_redemptions_per_user=max_redemptions_per_user,
            benefit_feature_key=benefit_feature_key,
            context=context,
            benefit_amount=_benefit_amount_for(benefit_amount),
        )

    def ensure_redeemable(self, *, at: datetime) -> None:
        if not self.active:
            raise PromotionRedemptionConflictError("비활성 프로모션입니다.")
        if self.starts_at > at:
            raise PromotionRedemptionConflictError("아직 시작되지 않은 프로모션입니다.")
        if self.expires_at is not None and self.expires_at <= at:
            raise PromotionRedemptionConflictError("만료된 프로모션입니다.")
        if self.max_redemptions is not None and self.times_redeemed >= self.max_redemptions:
            raise PromotionRedemptionConflictError("프로모션 사용 한도가 소진되었습니다.")

    def ensure_user_can_redeem(self, *, user_redemption_count: int) -> None:
        if user_redemption_count >= self.max_redemptions_per_user:
            raise PromotionRedemptionConflictError("이미 사용한 프로모션입니다.")

    def record_redemption(self) -> None:
        self.times_redeemed += 1


@dataclass(eq=False, slots=True)  # noqa: RUF100  # noqa: MUTABLE_OK
class PromotionContent(Entity[UUID]):
    promotion_id: UUID
    banner_image_url: str | None


@dataclass(eq=False, slots=True)  # noqa: RUF100  # noqa: MUTABLE_OK
class PromotionCode(AggregateRoot[UUID]):
    promotion_id: UUID
    code: str
    active: bool
    starts_at: datetime | None
    expires_at: datetime | None
    max_redemptions: int | None
    times_redeemed: int

    def ensure_redeemable(self, *, at: datetime) -> None:
        if not self.active:
            raise PromotionRedemptionConflictError("비활성 프로모션 코드입니다.")
        if self.starts_at is not None and self.starts_at > at:
            raise PromotionRedemptionConflictError("아직 사용할 수 없는 프로모션 코드입니다.")
        if self.expires_at is not None and self.expires_at <= at:
            raise PromotionRedemptionConflictError("만료된 프로모션 코드입니다.")
        if self.max_redemptions is not None and self.times_redeemed >= self.max_redemptions:
            raise PromotionRedemptionConflictError("프로모션 코드 사용 한도가 소진되었습니다.")

    def record_redemption(self) -> None:
        self.times_redeemed += 1


@dataclass(eq=False, slots=True)  # noqa: RUF100  # noqa: MUTABLE_OK
class PromotionRedemption(AggregateRoot[UUID]):
    promotion_id: UUID
    promotion_code_id: UUID | None
    user_id: UUID
    status: PromotionRedemptionStatus
    idempotency_key: str
    failure_reason: str | None
    redeemed_at: datetime | None

    @classmethod
    def restore(
        cls,
        *,
        redemption_id: UUID,
        promotion_id: UUID,
        promotion_code_id: UUID | None,
        user_id: UUID,
        status: PromotionRedemptionStatus,
        idempotency_key: str,
        failure_reason: str | None,
        redeemed_at: datetime | None,
    ) -> "PromotionRedemption":
        return cls(
            id=redemption_id,
            promotion_id=promotion_id,
            promotion_code_id=promotion_code_id,
            user_id=user_id,
            status=status,
            idempotency_key=idempotency_key,
            failure_reason=failure_reason,
            redeemed_at=redeemed_at,
        )

    @classmethod
    def create_granted(
        cls,
        *,
        promotion_id: UUID,
        promotion_code_id: UUID | None,
        user_id: UUID,
        idempotency_key: str,
        redeemed_at: datetime,
        benefit_amount: int,
        redemption_id: UUID | None = None,
    ) -> "PromotionRedemption":
        redemption = cls(
            id=redemption_id or uuid4(),
            promotion_id=promotion_id,
            promotion_code_id=promotion_code_id,
            user_id=user_id,
            status=PromotionRedemptionStatus.GRANTED,
            idempotency_key=idempotency_key,
            failure_reason=None,
            redeemed_at=redeemed_at,
        )
        redemption.record_event(
            PromotionRedemptionGranted(
                redemption_id=redemption.id,
                promotion_id=redemption.promotion_id,
                user_id=redemption.user_id,
                promotion_code_id=redemption.promotion_code_id,
                benefit_amount=benefit_amount,
                idempotency_key=redemption.idempotency_key,
            )
        )
        return redemption


def _benefit_amount_for(
    value: int | PromotionBenefitAmount,
    *,
    field_name: str = "benefit_amount",
) -> PromotionBenefitAmount:
    match value:
        case PromotionBenefitAmount():
            return value
        case int():
            return PromotionBenefitAmount(value=value, field_name=field_name)
        case unreachable:
            assert_never(unreachable)

from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel
from app.modules.promotions.application.commands.create_promotion_redemption.result import (
    CreatePromotionRedemptionResult,
)
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.result import (
    GetCurrentOcrCreditPromotionResult,
)
from app.modules.promotions.domain.model import PromotionBenefitFeatureKey


class PromotionState(StrEnum):
    REDEEMABLE = "redeemable"
    ALREADY_REDEEMED = "alreadyRedeemed"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


class PromotionListQuery(AppBaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    benefit_feature_key: PromotionBenefitFeatureKey = Field(
        alias="featureKey",
        description="조회할 혜택 기능. 현재는 OCR만 지원한다.",
    )


class PromotionCodeRedemptionRequest(AppBaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={"examples": [{"code": "WELCOME2026"}]},
    )

    code: str = Field(
        description="사용자가 입력한 프로모션 코드.",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class PromotionBenefitResponse(AppBaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    feature_key: PromotionBenefitFeatureKey = Field(alias="featureKey")
    amount: int


class PromotionRedemptionResponse(AppBaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    remaining_redemptions: int | None = Field(default=None, alias="remainingRedemptions")


class PromotionBalanceResponse(AppBaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    total_granted_count: int | None = Field(default=None, alias="totalGrantedCount")
    remaining_count: int | None = Field(default=None, alias="remainingCount")


class PromotionBannerImageResponse(AppBaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    image_url: str = Field(alias="imageUrl")


class PromotionResponse(AppBaseModel):
    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "state": "redeemable",
                    "promotionId": "00000000-0000-0000-0000-000000000201",
                    "benefit": {"featureKey": "ocr", "amount": 3},
                    "redemption": {"remainingRedemptions": 10},
                    "balance": None,
                    "bannerImage": {
                        "imageUrl": ("/api/v1/files/00000000-0000-0000-0000-000000000901/content")
                    },
                }
            ]
        },
    )

    state: PromotionState
    promotion_id: UUID | None = Field(default=None, alias="promotionId")
    benefit: PromotionBenefitResponse | None
    redemption: PromotionRedemptionResponse
    balance: PromotionBalanceResponse | None
    banner_image: PromotionBannerImageResponse | None = Field(default=None, alias="bannerImage")

    @classmethod
    def unavailable(cls) -> "PromotionResponse":
        return cls(
            state=PromotionState.UNAVAILABLE,
            promotionId=None,
            benefit=None,
            redemption=PromotionRedemptionResponse(),
            balance=None,
            bannerImage=None,
        )

    @classmethod
    def from_current_result(
        cls,
        result: GetCurrentOcrCreditPromotionResult,
        *,
        banner_image_url: str | None,
    ) -> "PromotionResponse":
        state = (
            PromotionState.ALREADY_REDEEMED
            if result.already_redeemed
            else PromotionState.REDEEMABLE
        )
        return cls(
            state=state,
            promotionId=result.promotion_id,
            benefit=PromotionBenefitResponse(
                featureKey=PromotionBenefitFeatureKey.OCR,
                amount=result.benefit_amount,
            ),
            redemption=PromotionRedemptionResponse(
                remainingRedemptions=result.remaining_redemptions,
            ),
            balance=None,
            bannerImage=_banner_image_response(banner_image_url),
        )

    @classmethod
    def from_redemption_result(
        cls,
        result: CreatePromotionRedemptionResult,
        *,
        banner_image_url: str | None,
    ) -> "PromotionResponse":
        return cls(
            state=PromotionState.ALREADY_REDEEMED,
            promotionId=result.promotion_id,
            benefit=PromotionBenefitResponse(
                featureKey=PromotionBenefitFeatureKey.OCR,
                amount=result.benefit_amount,
            ),
            redemption=PromotionRedemptionResponse(
                remainingRedemptions=result.remaining_redemptions,
            ),
            balance=PromotionBalanceResponse(
                totalGrantedCount=result.credit_balance_after,
                remainingCount=result.credit_remaining_after,
            ),
            bannerImage=_banner_image_response(banner_image_url),
        )


def _banner_image_response(image_url: str | None) -> PromotionBannerImageResponse | None:
    if image_url is None:
        return None
    return PromotionBannerImageResponse(imageUrl=image_url)

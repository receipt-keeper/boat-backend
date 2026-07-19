from dataclasses import dataclass
from typing import Annotated, assert_never
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from app.core.config.dependencies import get_request_settings
from app.core.config.settings import Settings
from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.promotions.api.schemas import (
    PromotionCodeRedemptionRequest,
    PromotionListQuery,
    PromotionQueryContext,
    PromotionResponse,
)
from app.modules.promotions.application.commands.create_promotion_code_redemption.command import (
    CreatePromotionCodeRedemptionCommand,
)
from app.modules.promotions.application.commands.create_promotion_redemption.command import (
    CreatePromotionRedemptionCommand,
)
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.query import (
    GetCurrentOcrCreditPromotionQuery,
)
from app.modules.promotions.dependencies import (
    CreatePromotionCodeRedemptionCommandUseCaseDep,
    CreatePromotionRedemptionCommandUseCaseDep,
    CurrentOcrCreditPromotionQueryUseCaseDep,
)
from app.modules.promotions.domain.model import PromotionContext, PromotionKind

_OpenApiResponse = dict[str, type[CommonResponse[ApiErrorData]] | str]

_ERROR_RESPONSES: dict[int | str, _OpenApiResponse] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": CommonResponse[ApiErrorData],
        "description": "인증 실패",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": CommonResponse[ApiErrorData],
        "description": "프로모션 또는 프로모션 코드를 찾을 수 없음",
    },
    status.HTTP_409_CONFLICT: {
        "model": CommonResponse[ApiErrorData],
        "description": "프로모션을 사용할 수 없음",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": CommonResponse[ApiErrorData],
        "description": "검증 실패 - 요청 형식 오류 또는 도메인 검증 실패",
    },
}


@dataclass(frozen=True, slots=True)
class PromotionApiContext:
    user_id: UUID
    api_prefix: str


async def get_promotion_api_context(
    principal: CurrentPrincipalDep,
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> PromotionApiContext:
    return PromotionApiContext(
        user_id=principal.user_id,
        api_prefix=settings.api_prefix.rstrip("/"),
    )


PromotionApiContextDep = Annotated[
    PromotionApiContext,
    Depends(get_promotion_api_context),
]


router = APIRouter(
    prefix="/promotions",
    tags=["promotions"],
    responses=_ERROR_RESPONSES,
)


@router.get(
    "",
    response_model=CommonResponse[PromotionResponse],
    summary="OCR 프로모션 상태 조회",
    description=(
        "앱이 OCR 혜택 수령 가능 여부와 지급 크레딧 수량을 판단할 수 있는 상태 값을 반환한다. "
        "GET /api/v1/usage에서 ocr.canAnalyze=false이면 "
        "GET /api/v1/promotions?featureKey=ocr&context=recharge로 월간 OCR 크레딧 "
        "충전 혜택을 조회하고, state=redeemable일 때 프로모션 ID로 수령을 요청한다."
    ),
)
async def get_promotions(
    query: Annotated[PromotionListQuery, Query()],
    context: PromotionApiContextDep,
    query_use_case: CurrentOcrCreditPromotionQueryUseCaseDep,
) -> CommonResponse[PromotionResponse]:
    result = await query_use_case.execute(
        GetCurrentOcrCreditPromotionQuery(
            user_id=context.user_id,
            context=_to_domain_promotion_context(query.context),
            kind=_to_domain_promotion_kind(query.context, query.kind),
        )
    )
    data = (
        PromotionResponse.unavailable()
        if result is None
        else PromotionResponse.from_current_result(
            result,
            banner_image_url=_with_api_prefix(context.api_prefix, result.banner_image_url),
        )
    )
    return CommonResponse(success=True, status=status.HTTP_200_OK, data=data)


@router.post(
    "/redemptions",
    response_model=CommonResponse[PromotionResponse],
    summary="프로모션 코드로 OCR 혜택 받기",
    description="사용자가 입력한 프로모션 코드로 OCR 크레딧 혜택을 요청한다.",
)
async def create_promotion_code_redemption(
    payload: PromotionCodeRedemptionRequest,
    context: PromotionApiContextDep,
    command_use_case: CreatePromotionCodeRedemptionCommandUseCaseDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CommonResponse[PromotionResponse]:
    result = await command_use_case.execute(
        CreatePromotionCodeRedemptionCommand(
            user_id=context.user_id,
            code=payload.code,
            idempotency_key=idempotency_key,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=PromotionResponse.from_redemption_result(
            result,
            banner_image_url=_with_api_prefix(context.api_prefix, result.banner_image_url),
        ),
    )


@router.post(
    "/{promotion_id}/redemptions",
    response_model=CommonResponse[PromotionResponse],
    summary="OCR 프로모션 혜택 받기",
    description=(
        "프로모션 ID로 OCR 크레딧 혜택을 요청한다. 월간 OCR 크레딧 충전은 "
        "GET /api/v1/promotions?featureKey=ocr&context=recharge 응답의 promotionId를 사용하며, "
        "중복 요청 방지를 위해 Idempotency-Key 헤더를 함께 보낸다."
    ),
)
async def create_promotion_redemption(
    promotion_id: UUID,
    context: PromotionApiContextDep,
    command_use_case: CreatePromotionRedemptionCommandUseCaseDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CommonResponse[PromotionResponse]:
    result = await command_use_case.execute(
        CreatePromotionRedemptionCommand(
            user_id=context.user_id,
            promotion_id=promotion_id,
            idempotency_key=idempotency_key,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=PromotionResponse.from_redemption_result(
            result,
            banner_image_url=_with_api_prefix(context.api_prefix, result.banner_image_url),
        ),
    )


def _with_api_prefix(api_prefix: str, path: str | None) -> str | None:
    if path is None or not path.startswith("/"):
        return path
    return f"{api_prefix}{path}"


def _to_domain_promotion_context(
    context: PromotionQueryContext | None,
) -> PromotionContext | None:
    match context:
        case PromotionQueryContext.RECHARGE:
            return PromotionContext.RECHARGE
        case None:
            return None
        case unreachable:
            assert_never(unreachable)


def _to_domain_promotion_kind(
    context: PromotionQueryContext | None,
    kind: PromotionKind | None,
) -> PromotionKind | None:
    if context == PromotionQueryContext.RECHARGE and kind is None:
        return PromotionKind.MONTHLY_ALLOWANCE
    return kind

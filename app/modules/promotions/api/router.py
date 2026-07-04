from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.promotions.api.schemas import (
    PromotionCodeRedemptionRequest,
    PromotionListQuery,
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

router = APIRouter(
    prefix="/promotions",
    tags=["promotions"],
    responses=_ERROR_RESPONSES,
)


@router.get(
    "",
    response_model=CommonResponse[PromotionResponse],
    summary="OCR 프로모션 상태 조회",
    description="앱이 OCR 혜택 수령 가능 여부와 지급 수량을 판단할 수 있는 상태 값을 반환한다.",
)
async def get_promotions(
    query: Annotated[PromotionListQuery, Query()],
    principal: CurrentPrincipalDep,
    query_use_case: CurrentOcrCreditPromotionQueryUseCaseDep,
) -> CommonResponse[PromotionResponse]:
    result = await query_use_case.execute(
        GetCurrentOcrCreditPromotionQuery(user_id=principal.user_id)
    )
    data = (
        PromotionResponse.unavailable()
        if result is None
        else PromotionResponse.from_current_result(result)
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
    principal: CurrentPrincipalDep,
    command_use_case: CreatePromotionCodeRedemptionCommandUseCaseDep,
) -> CommonResponse[PromotionResponse]:
    result = await command_use_case.execute(
        CreatePromotionCodeRedemptionCommand(
            user_id=principal.user_id,
            code=payload.code,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=PromotionResponse.from_redemption_result(result),
    )


@router.post(
    "/{promotion_id}/redemptions",
    response_model=CommonResponse[PromotionResponse],
    summary="OCR 프로모션 혜택 받기",
    description="프로모션 ID로 OCR 크레딧 혜택을 요청한다.",
)
async def create_promotion_redemption(
    promotion_id: UUID,
    principal: CurrentPrincipalDep,
    command_use_case: CreatePromotionRedemptionCommandUseCaseDep,
) -> CommonResponse[PromotionResponse]:
    result = await command_use_case.execute(
        CreatePromotionRedemptionCommand(
            user_id=principal.user_id,
            promotion_id=promotion_id,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=PromotionResponse.from_redemption_result(result),
    )

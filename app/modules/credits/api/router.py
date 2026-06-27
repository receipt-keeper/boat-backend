from fastapi import APIRouter, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.credits.api.schemas import (
    CreditsResponse,
    CreditTransactionResponse,
    CreditTransactionsResponse,
)
from app.modules.credits.mock import SAMPLE_CREDIT_BALANCE, SAMPLE_CREDIT_TRANSACTIONS

_OpenApiResponse = dict[str, type[CommonResponse[ApiErrorData]] | str]

_ERROR_RESPONSES: dict[int | str, _OpenApiResponse] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": CommonResponse[ApiErrorData],
        "description": "인증 실패",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": CommonResponse[ApiErrorData],
        "description": "검증 실패 - 요청 형식 오류 또는 도메인 검증 실패",
    },
}

router = APIRouter(
    prefix="/credits",
    tags=["credits"],
    responses=_ERROR_RESPONSES,
)


@router.get(
    "",
    response_model=CommonResponse[CreditsResponse],
    summary="크레딧 잔여 횟수 조회",
    description="무료 영수증 분석에 쓸 수 있는 전체 지급 횟수, 사용 횟수, 남은 횟수를 반환한다.",
)
async def get_credits() -> CommonResponse[CreditsResponse]:
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=CreditsResponse.from_domain(SAMPLE_CREDIT_BALANCE),
    )


@router.get(
    "/transactions",
    response_model=CommonResponse[CreditTransactionsResponse],
    summary="크레딧 지급/사용 내역 조회",
    description="퀴즈 보상처럼 크레딧이 추가되거나 사용된 내역을 반환한다.",
)
async def list_credit_transactions() -> CommonResponse[CreditTransactionsResponse]:
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=CreditTransactionsResponse(
            transactions=[
                CreditTransactionResponse.from_domain(transaction)
                for transaction in SAMPLE_CREDIT_TRANSACTIONS
            ],
        ),
    )

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse, CursorPaginationResponse
from app.modules.credits.api.schemas import (
    CreditsResponse,
    CreditTransactionListQuery,
    CreditTransactionResponse,
    CreditTransactionsResponse,
)
from app.modules.credits.application.queries.get_credit_balance.query import (
    GetCreditBalanceQuery,
)
from app.modules.credits.application.queries.list_credit_transactions.query import (
    ListCreditTransactionsQuery,
)
from app.modules.credits.dependencies import (
    GetCreditBalanceQueryUseCaseDep,
    ListCreditTransactionsQueryUseCaseDep,
)

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
    summary="크레딧 잔액 조회",
    description=(
        "기능 크레딧의 전체 지급 횟수, 사용 횟수, 남은 횟수를 반환한다. "
        "현재 MVP는 featureKey=ocr 기준으로 조회한다."
    ),
)
async def get_credits(
    principal: CurrentPrincipalDep,
    query_use_case: GetCreditBalanceQueryUseCaseDep,
) -> CommonResponse[CreditsResponse]:
    balance = await query_use_case.execute(GetCreditBalanceQuery(user_id=principal.user_id))
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=CreditsResponse.from_domain(balance),
    )


@router.get(
    "/transactions",
    response_model=CommonResponse[CreditTransactionsResponse],
    summary="크레딧 지급/사용 내역 조회",
    description=(
        "기능 크레딧이 지급되거나 사용된 내역을 커서 페이지로 반환한다. "
        "현재 MVP는 featureKey=ocr 기준으로 조회한다."
    ),
)
async def list_credit_transactions(
    query: Annotated[CreditTransactionListQuery, Query()],
    principal: CurrentPrincipalDep,
    query_use_case: ListCreditTransactionsQueryUseCaseDep,
) -> CommonResponse[CreditTransactionsResponse]:
    page = await query_use_case.execute(
        ListCreditTransactionsQuery(
            user_id=principal.user_id,
            cursor=query.cursor,
            limit=query.limit,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=CreditTransactionsResponse(
            transactions=[
                CreditTransactionResponse.from_list_item(transaction)
                for transaction in page.transactions
            ],
            pagination=CursorPaginationResponse(
                nextCursor=page.next_cursor,
                hasNext=page.has_next,
                limit=page.limit,
                totalCount=page.total_count,
            ),
        ),
    )

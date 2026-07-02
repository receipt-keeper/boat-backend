from fastapi import APIRouter, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.usage.api.schemas import UsageResponse
from app.modules.usage.application.queries.get_usage_snapshot.query import (
    GetUsageSnapshotQuery,
)
from app.modules.usage.dependencies import GetUsageSnapshotQueryUseCaseDep

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
    prefix="/usage",
    tags=["usage"],
    responses=_ERROR_RESPONSES,
)


@router.get(
    "",
    response_model=CommonResponse[UsageResponse],
    summary="기능 사용 가능 여부 조회",
    description="영수증 분석처럼 횟수 제한이 있는 기능의 남은 횟수와 사용 가능 여부를 반환한다.",
)
async def get_usage(
    principal: CurrentPrincipalDep,
    query_use_case: GetUsageSnapshotQueryUseCaseDep,
) -> CommonResponse[UsageResponse]:
    usage = await query_use_case.execute(GetUsageSnapshotQuery(user_id=principal.user_id))
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=UsageResponse.from_domain(usage),
    )

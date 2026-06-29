from typing import Final

from fastapi import APIRouter, status

from app.core.http.responses import ApiErrorData, CommonResponse

_FORCED_SERVER_ERROR_MESSAGE: Final = "테스트용 서버 오류를 강제로 발생시켰습니다."

router = APIRouter(
    prefix="/example",
    tags=["example"],
)


@router.get(
    "/server-error",
    response_model=CommonResponse[ApiErrorData],
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    summary="테스트용 500 오류 발생",
    description="클라이언트의 서버 오류 처리 확인을 위해 500 응답을 강제로 발생시킨다.",
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": CommonResponse[ApiErrorData],
            "description": "서버 내부 오류 강제 발생",
        },
    },
)
async def force_server_error() -> CommonResponse[ApiErrorData]:
    raise RuntimeError(_FORCED_SERVER_ERROR_MESSAGE)

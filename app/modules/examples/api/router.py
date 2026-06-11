from uuid import UUID

from fastapi import APIRouter, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.examples.api.schemas import CreateExampleUserRequest, ExampleUserResponse
from app.modules.examples.dependencies import ExampleUserServiceDep

router = APIRouter(
    prefix="/examples",
    tags=["examples"],
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": CommonResponse[ApiErrorData],
            "description": "검증 실패 — 요청 형식 오류 또는 도메인 검증 실패",
        },
    },
)


@router.get(
    "/{example_user_id}",
    response_model=CommonResponse[ExampleUserResponse],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": CommonResponse[ApiErrorData],
            "description": "예시 사용자를 찾을 수 없음",
        },
    },
)
async def get_example_user(
    example_user_id: UUID,
    service: ExampleUserServiceDep,
) -> CommonResponse[ExampleUserResponse]:
    example_user = await service.get_example_user(example_user_id)
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=ExampleUserResponse(
            id=example_user.id,
            nickname=example_user.nickname.value,
            email=example_user.email.value,
        ),
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CommonResponse[ExampleUserResponse],
)
async def create_example_user(
    request: CreateExampleUserRequest,
    service: ExampleUserServiceDep,
) -> CommonResponse[ExampleUserResponse]:
    example_user = await service.create_example_user(
        nickname=request.nickname,
        email=request.email,
        password=request.password,
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_201_CREATED,
        data=ExampleUserResponse(
            id=example_user.id,
            nickname=example_user.nickname.value,
            email=example_user.email.value,
        ),
    )

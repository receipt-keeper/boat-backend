from typing import Any

from fastapi import APIRouter, Request, Response, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.dependencies import WithdrawAccountCommandUseCaseDep
from app.modules.users.api.schemas import (
    CurrentUserResponse,
    ProfileImageResponse,
    SetProfileImageRequest,
)
from app.modules.users.application.commands.update_profile_image.command import (
    ClearProfileImageCommand,
    SetProfileImageCommand,
)
from app.modules.users.application.queries.current_user_profile.query import CurrentUserProfileQuery
from app.modules.users.dependencies import (
    CurrentUserProfileQueryUseCaseDep,
    UpdateProfileImageCommandUseCaseDep,
)

# 모든 users 엔드포인트의 공통 에러 응답.
# 전역 예외 핸들러가 CommonResponse[ApiErrorData] 봉투로 변환한다.
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": CommonResponse[ApiErrorData],
        "description": "인증 실패",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": CommonResponse[ApiErrorData],
        "description": "사용자를 찾을 수 없음",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": CommonResponse[ApiErrorData],
        "description": "검증 실패 — 요청 형식 오류 또는 도메인 검증 실패",
    },
}

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses=_ERROR_RESPONSES,
)


@router.get(
    "/me",
    response_model=CommonResponse[CurrentUserResponse],
    summary="내 정보 조회",
    description="로그인한 계정의 프로필 정보를 반환한다.",
)
async def get_me(
    request: Request,
    principal: CurrentPrincipalDep,
    query_use_case: CurrentUserProfileQueryUseCaseDep,
) -> CommonResponse[CurrentUserResponse]:
    profile = await query_use_case.execute(CurrentUserProfileQuery(user_id=principal.user_id))
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=CurrentUserResponse(
            email=profile.email,
            name=profile.name,
            nickname=profile.nickname,
            profileImageUrl=_with_api_prefix(request, profile.profile_image_url),
        ),
    )


@router.put(
    "/me/profile-image",
    response_model=CommonResponse[ProfileImageResponse],
    summary="프로필 이미지 설정",
    description="업로드 파일을 프로필 이미지로 설정하고 프로필 이미지 경로를 반환한다.",
)
async def set_profile_image(
    request: Request,
    body: SetProfileImageRequest,
    principal: CurrentPrincipalDep,
    command_use_case: UpdateProfileImageCommandUseCaseDep,
) -> CommonResponse[ProfileImageResponse]:
    result = await command_use_case.set_profile_image(
        SetProfileImageCommand(user_id=principal.user_id, file_id=body.file_id)
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=ProfileImageResponse(
            profileImageUrl=_with_api_prefix(request, result.profile_image_url),
        ),
    )


@router.delete(
    "/me/profile-image",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="프로필 이미지 삭제",
    description="프로필 이미지를 제거한다. 성공하면 본문 없이 204를 반환한다.",
)
async def clear_profile_image(
    principal: CurrentPrincipalDep,
    command_use_case: UpdateProfileImageCommandUseCaseDep,
) -> Response:
    await command_use_case.clear_profile_image(ClearProfileImageCommand(user_id=principal.user_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="회원 탈퇴",
    description=(
        "로그인한 계정을 탈퇴 처리하고 로그인 정보와 사용자 계정 데이터를 삭제한다. "
        "성공하면 본문 없이 204를 반환한다."
    ),
)
async def withdraw_me(
    principal: CurrentPrincipalDep,
    command_use_case: WithdrawAccountCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(
        WithdrawAccountCommand(
            user_id=principal.user_id,
            credentials_id=principal.credentials_id,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _with_api_prefix(request: Request, path: str | None) -> str | None:
    if path is None or not path.startswith("/"):
        return path
    api_prefix = request.app.state.settings.api_prefix.rstrip("/")
    return f"{api_prefix}{path}"

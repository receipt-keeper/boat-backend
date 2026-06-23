from typing import Any

from fastapi import APIRouter, Response, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.auth.application.commands.withdraw.command import WithdrawAccountCommand
from app.modules.auth.dependencies import WithdrawAccountCommandUseCaseDep
from app.modules.users.api.schemas import (
    CurrentUserResponse,
    UpdateCurrentUserRequest,
    UpdateCurrentUserResponse,
)
from app.modules.users.application.commands.update_settings.command import UpdateSettingsCommand
from app.modules.users.application.queries.current_user_profile.query import CurrentUserProfileQuery
from app.modules.users.dependencies import (
    CurrentUserProfileQueryUseCaseDep,
    UpdateSettingsCommandUseCaseDep,
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
)
async def get_me(
    principal: CurrentPrincipalDep,
    query_use_case: CurrentUserProfileQueryUseCaseDep,
) -> CommonResponse[CurrentUserResponse]:
    """현재 로그인 사용자의 내 정보를 조회한다.

    이메일, 이름/닉네임, 프로필 이미지 URL, 마케팅 동의, 무료 분석 토큰 잔량을 반환한다.
    """
    profile = await query_use_case.execute(CurrentUserProfileQuery(user_id=principal.user_id))
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=CurrentUserResponse(
            email=profile.email,
            name=profile.name,
            nickname=profile.nickname,
            profileImageUrl=profile.profile_image_url,
            marketingConsent=profile.marketing_consent,
            freeAnalysisTokensRemaining=profile.free_analysis_tokens_remaining,
        ),
    )


@router.patch(
    "/me",
    response_model=CommonResponse[UpdateCurrentUserResponse],
)
async def update_me(
    request: UpdateCurrentUserRequest,
    principal: CurrentPrincipalDep,
    command_use_case: UpdateSettingsCommandUseCaseDep,
) -> CommonResponse[UpdateCurrentUserResponse]:
    """현재 로그인 사용자의 내 정보를 부분 수정한다.

    전달된 필드만 수정하며(None이면 기존 값 유지), 변경 결과를 즉시 DB에 반영한다.
    """
    settings = await command_use_case.execute(
        UpdateSettingsCommand(
            user_id=principal.user_id,
            notification_enabled=None,
            marketing_consent=request.marketing_consent,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=UpdateCurrentUserResponse(
            marketingConsent=settings.marketing_consent,
        ),
    )


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def withdraw_me(
    principal: CurrentPrincipalDep,
    command_use_case: WithdrawAccountCommandUseCaseDep,
) -> Response:
    """회원 탈퇴.

    인증 측(credential/session/refresh/external identity)과 users 측(설정/엔타이틀먼트/
    푸시 토큰/user row)을 한 트랜잭션에서 삭제한다. 성공 시 204, 실패 시 전체 롤백한다.
    """
    await command_use_case.execute(
        WithdrawAccountCommand(
            user_id=principal.user_id,
            credentials_id=principal.credentials_id,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from typing import Any

from fastapi import APIRouter, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.users.api.schemas import (
    UpdateSettingsRequest,
    UpdateSettingsResponse,
    UserProfileResponse,
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

# NOTE: 푸시 토큰 등록/삭제 API(POST /me/push-tokens, DELETE /me/push-tokens/{deviceId})는
# 알림 기능 착수 시점(추후)에 노출할 예정이라, 앱 개발자에게 보이지 않도록 라우터에 의도적으로
# 등록하지 않는다. 관련 use case(register_push_token / delete_push_token), DTO(RegisterPushToken*),
# dependency, repository, 도메인(UserPushToken) 코드는 모두 보존되어 있으므로 재노출 시
# 여기에 POST/DELETE 핸들러만 다시 추가하면 된다.


@router.get(
    "/me",
    response_model=CommonResponse[UserProfileResponse],
)
async def get_me(
    principal: CurrentPrincipalDep,
    query_use_case: CurrentUserProfileQueryUseCaseDep,
) -> CommonResponse[UserProfileResponse]:
    """현재 로그인 사용자의 마이페이지 정보를 조회한다.

    이메일, 프로필 이미지 URL, 무료 분석 토큰 잔량, 알림 설정, 마케팅 동의 등을 반환한다.
    """
    profile = await query_use_case.execute(CurrentUserProfileQuery(user_id=principal.user_id))
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=UserProfileResponse(
            email=profile.email,
            normalizedEmail=profile.normalized_email,
            name=profile.name,
            nickname=profile.nickname,
            profileImageUrl=profile.profile_image_url,
            notificationEnabled=profile.notification_enabled,
            marketingConsent=profile.marketing_consent,
            freeAnalysisTokensRemaining=profile.free_analysis_tokens_remaining,
            pushTokenCount=profile.push_token_count,
        ),
    )


@router.patch(
    "/me/settings",
    response_model=CommonResponse[UpdateSettingsResponse],
)
async def update_my_settings(
    request: UpdateSettingsRequest,
    principal: CurrentPrincipalDep,
    command_use_case: UpdateSettingsCommandUseCaseDep,
) -> CommonResponse[UpdateSettingsResponse]:
    """현재 로그인 사용자의 알림/마케팅 설정을 변경한다.

    전달된 필드만 부분 수정하며(None이면 기존 값 유지), 변경 결과를 즉시 DB에 반영한다.
    """
    settings = await command_use_case.execute(
        UpdateSettingsCommand(
            user_id=principal.user_id,
            notification_enabled=request.notification_enabled,
            marketing_consent=request.marketing_consent,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=UpdateSettingsResponse(
            notificationEnabled=settings.notification_enabled,
            marketingConsent=settings.marketing_consent,
        ),
    )

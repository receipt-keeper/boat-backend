from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class UserProfileResponse(AppBaseModel):
    """GET /users/me 응답. 마이페이지에 노출되는 사용자 정보 묶음."""

    model_config = ConfigDict(populate_by_name=True)

    # 대표 이메일
    email: str | None = Field(alias="email")
    # 정규화 이메일(소문자/trim)
    normalized_email: str | None = Field(alias="normalizedEmail")
    # 이름
    name: str | None = Field(alias="name")
    # 닉네임
    nickname: str | None = Field(alias="nickname")
    # 프로필 이미지 URL
    profile_image_url: str | None = Field(alias="profileImageUrl")
    # 알림 수신 설정
    notification_enabled: bool = Field(alias="notificationEnabled")
    # 마케팅 수신 동의
    marketing_consent: bool = Field(alias="marketingConsent")
    # 무료 분석 토큰 잔량
    free_analysis_tokens_remaining: int = Field(alias="freeAnalysisTokensRemaining")
    # 등록된 푸시 토큰 개수
    push_token_count: int = Field(alias="pushTokenCount")


class UpdateSettingsRequest(AppBaseModel):
    """PATCH /users/me/settings 요청. 부분 수정이며 미전달 필드는 기존 값을 유지한다."""

    model_config = ConfigDict(populate_by_name=True)

    # 알림 설정(미전달 시 기존 값 유지)
    notification_enabled: bool | None = Field(default=None, alias="notificationEnabled")
    # 마케팅 동의(미전달 시 기존 값 유지)
    marketing_consent: bool | None = Field(default=None, alias="marketingConsent")


class UpdateSettingsResponse(AppBaseModel):
    """PATCH /users/me/settings 응답. 실제 반영된 알림/마케팅 설정 값."""

    model_config = ConfigDict(populate_by_name=True)

    # 반영된 알림 설정
    notification_enabled: bool = Field(alias="notificationEnabled")
    # 반영된 마케팅 동의
    marketing_consent: bool = Field(alias="marketingConsent")


# NOTE: 아래 푸시 토큰 DTO는 알림 기능 착수 시점(추후)에 사용할 예정이다. 현재 users 라우터에는
# 푸시 토큰 API를 등록하지 않지만, 재노출에 대비해 전송 스키마 코드를 보존한다.
class RegisterPushTokenRequest(AppBaseModel):
    """POST /users/me/push-tokens 요청. FCM 푸시 토큰 등록(현재 미노출, 추후 사용)."""

    model_config = ConfigDict(populate_by_name=True)

    # 기기 식별자
    device_id: str = Field(alias="deviceId")
    # FCM 토큰
    fcm_token: str = Field(alias="fcmToken")
    # 플랫폼(android/ios/web)
    platform: str = Field(alias="platform")


class RegisterPushTokenResponse(AppBaseModel):
    """POST /users/me/push-tokens 응답. 등록/갱신된 푸시 토큰 ID(현재 미노출, 추후 사용)."""

    model_config = ConfigDict(populate_by_name=True)

    # 등록/갱신된 푸시 토큰 ID
    push_token_id: UUID = Field(alias="pushTokenId")

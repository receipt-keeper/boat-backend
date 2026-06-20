from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class UserProfileResponse(AppBaseModel):
    """마이페이지 사용자 정보 응답."""

    model_config = ConfigDict(populate_by_name=True)

    email: str | None = Field(
        alias="email",
        description="대표 이메일.",
    )
    normalized_email: str | None = Field(
        alias="normalizedEmail",
        description="정규화 이메일(소문자/공백 제거). 계정 식별/연결 기준 값.",
    )
    name: str | None = Field(
        alias="name",
        description="이름.",
    )
    nickname: str | None = Field(
        alias="nickname",
        description="닉네임.",
    )
    profile_image_url: str | None = Field(
        alias="profileImageUrl",
        description="프로필 이미지 URL.",
    )
    notification_enabled: bool = Field(
        alias="notificationEnabled",
        description="알림 수신 설정. true면 푸시 알림을 받는다.",
    )
    marketing_consent: bool = Field(
        alias="marketingConsent",
        description="마케팅 수신 동의 여부.",
    )
    free_analysis_tokens_remaining: int = Field(
        alias="freeAnalysisTokensRemaining",
        description="남은 무료 분석 토큰 수.",
        examples=[3],
    )
    push_token_count: int = Field(
        alias="pushTokenCount",
        description="등록된 푸시 토큰(기기) 개수.",
    )


class UpdateSettingsRequest(AppBaseModel):
    """마이페이지 설정 변경 요청. 부분 수정이며 미전달 필드는 기존 값을 유지한다."""

    model_config = ConfigDict(populate_by_name=True)

    notification_enabled: bool | None = Field(
        default=None,
        alias="notificationEnabled",
        description="알림 수신 설정. 미전달(null) 시 기존 값을 유지한다.",
    )
    marketing_consent: bool | None = Field(
        default=None,
        alias="marketingConsent",
        description="마케팅 수신 동의. 미전달(null) 시 기존 값을 유지한다.",
    )


class UpdateSettingsResponse(AppBaseModel):
    """마이페이지 설정 변경 응답. 실제 반영된 값."""

    model_config = ConfigDict(populate_by_name=True)

    notification_enabled: bool = Field(
        alias="notificationEnabled",
        description="반영된 알림 수신 설정.",
    )
    marketing_consent: bool = Field(
        alias="marketingConsent",
        description="반영된 마케팅 수신 동의.",
    )


# NOTE: 아래 푸시 토큰 DTO는 알림 기능 착수 시점(추후)에 사용할 예정이다. 현재 users 라우터에는
# 푸시 토큰 API를 등록하지 않지만, 재노출에 대비해 전송 스키마 코드를 보존한다.
class RegisterPushTokenRequest(AppBaseModel):
    """FCM 푸시 토큰 등록 요청(현재 미노출, 추후 사용)."""

    model_config = ConfigDict(populate_by_name=True)

    device_id: str = Field(
        alias="deviceId",
        description="기기 식별자. 같은 기기는 동일 deviceId로 upsert된다.",
        examples=["A1B2C3D4-DEVICE"],
    )
    fcm_token: str = Field(
        alias="fcmToken",
        description="FCM 등록 토큰.",
    )
    platform: str = Field(
        alias="platform",
        description="푸시 플랫폼.",
        examples=["android", "ios", "web"],
    )


class RegisterPushTokenResponse(AppBaseModel):
    """FCM 푸시 토큰 등록 응답(현재 미노출, 추후 사용)."""

    model_config = ConfigDict(populate_by_name=True)

    push_token_id: UUID = Field(
        alias="pushTokenId",
        description="등록 또는 갱신된 푸시 토큰 ID.",
    )

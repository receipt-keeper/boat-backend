from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel
from app.modules.notifications.domain.value_objects import NotificationTargetType, PushPlatform


class NotificationResponse(AppBaseModel):
    notification_id: UUID = Field(alias="notificationId", description="알림 ID.")
    kind: str = Field(description="알림 유형.")
    message: str = Field(description="알림 문구.")
    target_type: NotificationTargetType = Field(
        alias="targetType",
        description=(
            "알림 클릭 대상 유형. 보증 알림은 asset, 등록 유도는 receiptUpload, 대상이 없으면 none."
        ),
    )
    target_id: UUID | None = Field(alias="targetId", description="알림 클릭 대상 ID.")
    created_at: datetime = Field(alias="createdAt", description="알림 생성 시각.")
    read_at: datetime | None = Field(alias="readAt", description="알림 읽음 시각.")


class NotificationListResponse(AppBaseModel):
    notifications: list[NotificationResponse] = Field(description="알림 목록.")


class NotificationSettingsResponse(AppBaseModel):
    push_enabled: bool = Field(alias="pushEnabled", description="푸시 알림 수신 여부.")
    marketing_consent: bool = Field(
        alias="marketingConsent",
        description="마케팅 알림 수신 동의 여부.",
    )


class UpdateNotificationSettingsRequest(AppBaseModel):
    model_config = ConfigDict(extra="forbid")

    push_enabled: bool | None = Field(
        default=None,
        alias="pushEnabled",
        description="푸시 알림 수신 여부. 보내지 않으면 기존 값을 유지한다.",
    )
    marketing_consent: bool | None = Field(
        default=None,
        alias="marketingConsent",
        description="마케팅 알림 수신 동의 여부. 보내지 않으면 기존 값을 유지한다.",
    )


class RegisterPushDeviceRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "fcmToken": "fcm-token-sample",
                    "platform": PushPlatform.IOS.value,
                }
            ]
        },
    )

    fcm_token: str = Field(
        alias="fcmToken",
        min_length=1,
        max_length=512,
        description="푸시 알림 발송에 사용할 FCM 토큰.",
    )
    platform: PushPlatform = Field(description="푸시 토큰이 발급된 디바이스 플랫폼.")


class PushDeviceResponse(AppBaseModel):
    device_id: str = Field(alias="deviceId", description="앱이 전달한 기기 식별자.")
    registered: bool = Field(description="푸시 알림 발송 대상 등록 여부.")
    platform: PushPlatform = Field(description="등록된 디바이스 플랫폼.")

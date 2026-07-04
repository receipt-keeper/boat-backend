from datetime import datetime
from typing import Self, assert_never
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.core.http.responses import AppBaseModel, CursorPaginationResponse
from app.modules.notifications.domain.value_objects import (
    DevicePlatform,
    NotificationKind,
    NotificationTargetType,
)


class CreateNotificationRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "kind": "benefit",
                    "message": "이번 달 혜택을 확인해 보세요.",
                    "targetType": "none",
                    "targetId": None,
                }
            ]
        },
    )

    kind: NotificationKind = Field(
        description="생성할 알림 유형.",
        examples=["benefit"],
    )
    message: str = Field(
        description="사용자에게 표시할 알림 문구.",
        examples=["이번 달 혜택을 확인해 보세요."],
    )
    target_type: NotificationTargetType = Field(
        alias="targetType",
        description=(
            "알림 클릭 대상 유형. 영수증 상세는 receipt, "
            "등록 유도는 receiptUpload, 대상이 없으면 none."
        ),
        examples=["none"],
    )
    target_id: UUID | None = Field(
        default=None,
        alias="targetId",
        description="알림 클릭 대상 ID. 대상이 없거나 등록 유도 대상이면 null로 보낸다.",
        examples=[None],
    )

    @model_validator(mode="after")
    def validate_target_id_contract(self) -> Self:
        match self.target_type:
            case NotificationTargetType.RECEIPT:
                if self.target_id is None:
                    raise ValueError("receipt 대상 알림은 targetId가 필요합니다.")
            case NotificationTargetType.RECEIPT_UPLOAD | NotificationTargetType.NONE:
                if self.target_id is not None:
                    raise ValueError(
                        "receiptUpload 또는 none 대상 알림은 targetId를 보낼 수 없습니다."
                    )
            case unreachable:
                assert_never(unreachable)

        return self


class NotificationResponse(AppBaseModel):
    notification_id: UUID = Field(alias="notificationId", description="알림 ID.")
    kind: NotificationKind = Field(description="알림 유형.")
    message: str = Field(description="알림 문구.")
    target_type: NotificationTargetType = Field(
        alias="targetType",
        description=(
            "알림 클릭 대상 유형. 영수증 상세는 receipt, "
            "등록 유도는 receiptUpload, 대상이 없으면 none."
        ),
    )
    target_id: UUID | None = Field(alias="targetId", description="알림 클릭 대상 ID.")
    created_at: datetime = Field(alias="createdAt", description="알림 생성 시각.")
    read_at: datetime | None = Field(alias="readAt", description="알림 읽음 시각.")


class NotificationListQuery(AppBaseModel):
    model_config = ConfigDict(frozen=True)

    cursor: str | None = Field(
        default=None,
        description="다음 목록 조회용 keyset 커서. 첫 조회에서는 보내지 않는다.",
        min_length=1,
        max_length=200,
    )
    limit: int = Field(default=20, description="응답할 최대 알림 수.", ge=1, le=50)


class NotificationListResponse(AppBaseModel):
    notifications: list[NotificationResponse] = Field(description="알림 목록.")
    pagination: CursorPaginationResponse = Field(description="커서 기반 목록 정보.")


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


class RegisterDeviceRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "deviceId": "b3f3f7b0-6e33-4d3a-9a9a-8f6a2b5e9c11",
                    "fcmToken": "fcm-token-example",
                    "platform": "android",
                }
            ]
        },
    )

    device_id: str = Field(
        alias="deviceId",
        description="클라이언트가 발급한 디바이스 식별자.",
        examples=["b3f3f7b0-6e33-4d3a-9a9a-8f6a2b5e9c11"],
    )
    fcm_token: str = Field(
        alias="fcmToken",
        description="Firebase Cloud Messaging 디바이스 토큰.",
        examples=["fcm-token-example"],
    )
    platform: DevicePlatform = Field(
        description="디바이스 플랫폼.",
        examples=["android"],
    )

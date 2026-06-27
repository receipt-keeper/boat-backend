from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel, CursorPaginationResponse
from app.modules.notifications.domain.value_objects import NotificationTargetType


class NotificationResponse(AppBaseModel):
    notification_id: UUID = Field(alias="notificationId", description="알림 ID.")
    kind: str = Field(description="알림 유형.")
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
        description="다음 목록 조회용 커서. 첫 조회에서는 보내지 않는다.",
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

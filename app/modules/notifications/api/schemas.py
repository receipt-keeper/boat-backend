from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel, CursorPaginationResponse
from app.modules.notifications.domain.value_objects import (
    DevicePlatform,
    NotificationMessageType,
)


class CreateNotificationRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "messageType": "marketing",
                    "kind": "benefit",
                    "title": "혜택 안내",
                    "message": "이번 달 혜택을 확인해 보세요.",
                    "resourceType": None,
                    "resourceId": None,
                    "metadata": {},
                }
            ]
        },
    )

    message_type: NotificationMessageType = Field(
        alias="messageType",
        description=(
            "알림 메시지 유형. transactional=거래성(사용자 행동에서 파생, 동의 불필요), "
            "marketing=광고성(마케팅 수신 동의 필요). 마케팅 수신 동의 게이트는 이 값으로만 "
            "집행된다. 참고: transactional은 결제나 DB 처리 단위와 무관한 메시징 업계 용어다."
        ),
        examples=["marketing"],
    )
    kind: str = Field(
        description="생성할 알림 유형을 나타내는 발신자 소유 식별자.",
        min_length=1,
        max_length=50,
        examples=["benefit"],
    )
    title: str = Field(
        description="푸시 알림에 표시할 제목. 발신자가 완성된 문구로 제공한다.",
        min_length=1,
        max_length=100,
        examples=["혜택 안내"],
    )
    message: str = Field(
        description="사용자에게 표시할 알림 문구.",
        examples=["이번 달 혜택을 확인해 보세요."],
    )
    resource_type: str | None = Field(
        default=None,
        alias="resourceType",
        description="알림이 참조하는 리소스 유형. resourceId와 함께 있거나 함께 없어야 한다.",
        examples=[None],
    )
    resource_id: UUID | None = Field(
        default=None,
        alias="resourceId",
        description="알림이 참조하는 리소스 ID. resourceType과 함께 있거나 함께 없어야 한다.",
        examples=[None],
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "발신자 소유 부가 정보. 서버는 형식만 검증한다(최대 50키, 키 1~40자, 값 500자 이하). "
            "내용의 의미는 해석하지 않는다."
        ),
        examples=[{}],
    )


class NotificationResponse(AppBaseModel):
    notification_id: UUID = Field(alias="notificationId", description="알림 ID.")
    message_type: NotificationMessageType = Field(
        alias="messageType",
        description=(
            "알림 메시지 유형. transactional=거래성(사용자 행동에서 파생, 동의 불필요), "
            "marketing=광고성(마케팅 수신 동의 필요)."
        ),
    )
    kind: str = Field(description="알림 유형을 나타내는 발신자 소유 식별자.")
    title: str = Field(description="알림 제목.")
    message: str = Field(description="알림 문구.")
    resource_type: str | None = Field(
        alias="resourceType",
        description="알림이 참조하는 리소스 유형.",
    )
    resource_id: UUID | None = Field(
        alias="resourceId",
        description="알림이 참조하는 리소스 ID.",
    )
    metadata: dict[str, str] = Field(
        description=(
            "발신자 소유 부가 정보. 서버는 형식만 검증하며 내용의 의미는 해석하지 않는다. "
            "값이 없으면 빈 객체다."
        ),
    )
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
                    "token": "c8z9HXZRSE2jciNYw6yPAD:APA91b...",
                    "platform": "android",
                }
            ]
        },
    )

    token: str = Field(
        description=("FCM registration token. FirebaseMessaging에서 발급받은 기기 등록 토큰."),
        examples=["c8z9HXZRSE2jciNYw6yPAD:APA91b..."],
    )
    platform: DevicePlatform = Field(
        description="디바이스 플랫폼.",
        examples=["android"],
    )

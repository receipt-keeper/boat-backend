from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from app.modules.notifications.api.schemas import NotificationResponse
from app.modules.notifications.domain.value_objects import NotificationKind, NotificationTargetType

MOCK_NOTIFICATION_ID: Final = UUID("00000000-0000-0000-0000-000000000601")
MOCK_RECEIPT_ID: Final = UUID("00000000-0000-0000-0000-000000000301")

SAMPLE_NOTIFICATIONS: Final[tuple[NotificationResponse, ...]] = (
    NotificationResponse(
        notificationId=MOCK_NOTIFICATION_ID,
        kind=NotificationKind.WARRANTY_WARNING,
        message=(
            "삼성 냉장고 875L 무상 AS 14일 남았어요! 기간이 지나기 전 영수증 증빙 서류를 챙기세요."
        ),
        targetType=NotificationTargetType.RECEIPT,
        targetId=MOCK_RECEIPT_ID,
        createdAt=datetime(2026, 5, 12, 9, 0, tzinfo=UTC),
        readAt=None,
    ),
    NotificationResponse(
        notificationId=UUID("00000000-0000-0000-0000-000000000602"),
        kind=NotificationKind.REGISTRATION_PROMPT,
        message="영수증을 등록하면 무상 AS 만료일을 놓치지 않도록 알려드려요.",
        targetType=NotificationTargetType.RECEIPT_UPLOAD,
        targetId=None,
        createdAt=datetime(2026, 5, 13, 9, 0, tzinfo=UTC),
        readAt=None,
    ),
    NotificationResponse(
        notificationId=UUID("00000000-0000-0000-0000-000000000603"),
        kind=NotificationKind.CREDIT_PROMPT,
        message="새 알림이 있습니다.",
        targetType=NotificationTargetType.NONE,
        targetId=None,
        createdAt=datetime(2026, 5, 14, 9, 0, tzinfo=UTC),
        readAt=None,
    ),
)


def notification_with_read_state(
    *,
    notification_id: UUID,
    read_at: datetime | None,
) -> NotificationResponse:
    base_notification = SAMPLE_NOTIFICATIONS[0]
    return NotificationResponse(
        notificationId=notification_id,
        kind=base_notification.kind,
        message=base_notification.message,
        targetType=base_notification.target_type,
        targetId=base_notification.target_id,
        createdAt=base_notification.created_at,
        readAt=read_at,
    )

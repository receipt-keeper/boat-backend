from datetime import UTC, datetime
from uuid import uuid4

from app.modules.notifications.domain.model import UserNotification
from app.modules.notifications.domain.value_objects import NotificationMessageType
from app.modules.notifications.tests.test_application import (
    TEST_USER_ID,
    InMemoryNotificationRepository,
)


async def test_notification_repository_deletes_notification_for_owner() -> None:
    # Given: 현재 사용자가 소유한 알림이 저장되어 있다.
    repository = InMemoryNotificationRepository()
    notification = UserNotification.create(
        user_id=TEST_USER_ID,
        message_type=NotificationMessageType.TRANSACTIONAL,
        kind="benefit",
        title="혜택 안내",
        message="혜택을 확인해 보세요.",
        created_at=datetime(2026, 7, 17, tzinfo=UTC),
    )
    repository.notifications[notification.id] = notification

    # When: 소유자 기준으로 알림을 삭제한다.
    deleted = await repository.delete_by_id_for_user(
        notification_id=notification.id,
        user_id=TEST_USER_ID,
    )

    # Then: 삭제 성공을 반환하고 저장소에서 제거된다.
    assert deleted is True
    assert notification.id not in repository.notifications


async def test_notification_repository_does_not_delete_foreign_notification() -> None:
    # Given: 다른 사용자가 소유한 알림이 저장되어 있다.
    repository = InMemoryNotificationRepository()
    notification = UserNotification.create(
        user_id=uuid4(),
        message_type=NotificationMessageType.TRANSACTIONAL,
        kind="benefit",
        title="혜택 안내",
        message="혜택을 확인해 보세요.",
        created_at=datetime(2026, 7, 17, tzinfo=UTC),
    )
    repository.notifications[notification.id] = notification

    # When: 현재 사용자가 다른 사용자의 알림 삭제를 시도한다.
    deleted = await repository.delete_by_id_for_user(
        notification_id=notification.id,
        user_id=TEST_USER_ID,
    )

    # Then: 삭제되지 않고 실패를 반환한다.
    assert deleted is False
    assert notification.id in repository.notifications

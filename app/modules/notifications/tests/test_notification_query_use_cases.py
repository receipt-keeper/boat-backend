from app.modules.notifications.application.queries.get_notification_settings.query import (
    GetNotificationSettingsQuery,
)
from app.modules.notifications.application.queries.get_notification_settings.use_case import (
    GetNotificationSettingsQueryUseCase,
)
from app.modules.notifications.application.queries.list_notifications.query import (
    ListNotificationsQuery,
)
from app.modules.notifications.application.queries.list_notifications.use_case import (
    ListNotificationsQueryUseCase,
)
from app.modules.notifications.domain.model import NotificationSettings, UserNotification
from app.modules.notifications.domain.value_objects import NotificationKind
from app.modules.notifications.tests.test_application import (
    CREATED_AT,
    TEST_USER_ID,
    InMemoryNotificationRepository,
)


async def test_list_notifications_returns_user_page_without_writes() -> None:
    # Given: 현재 사용자에게 알림이 저장되어 있다.
    repository = InMemoryNotificationRepository()
    notification = UserNotification.create(
        user_id=TEST_USER_ID,
        kind=NotificationKind.WARRANTY_NOTICE,
        message="보증 만료가 다가옵니다.",
        created_at=CREATED_AT,
    )
    repository.notifications[notification.id] = notification

    # When: 알림 목록 query를 실행한다.
    result = await ListNotificationsQueryUseCase(notification_repository=repository).execute(
        ListNotificationsQuery(user_id=TEST_USER_ID, limit=10)
    )

    # Then: 목록 결과를 반환하고 write repository method는 호출하지 않는다.
    assert [item.notification_id for item in result.notifications] == [notification.id]
    assert result.total_count == 1
    assert repository.create_count == 0
    assert repository.mark_read_count == 0
    assert repository.update_settings_count == 0


async def test_get_settings_returns_current_settings_without_writes() -> None:
    # Given: 현재 사용자의 NotificationSettings가 저장되어 있다.
    repository = InMemoryNotificationRepository()
    repository.settings[TEST_USER_ID] = NotificationSettings.create(
        user_id=TEST_USER_ID,
        push_enabled=False,
        marketing_consent=True,
    )

    # When: 알림 설정 query를 실행한다.
    result = await GetNotificationSettingsQueryUseCase(notification_repository=repository).execute(
        GetNotificationSettingsQuery(user_id=TEST_USER_ID)
    )

    # Then: 설정 결과를 반환하고 write repository method는 호출하지 않는다.
    assert result.push_enabled is False
    assert result.marketing_consent is True
    assert repository.create_count == 0
    assert repository.mark_read_count == 0
    assert repository.update_settings_count == 0

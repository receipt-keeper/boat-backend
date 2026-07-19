from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.domain.exceptions import NotFoundError
from app.modules.notifications.application.commands.delete_notification.command import (
    DeleteNotificationCommand,
)
from app.modules.notifications.application.commands.delete_notification.use_case import (
    DeleteNotificationCommandUseCase,
)
from app.modules.notifications.domain.model import UserNotification
from app.modules.notifications.domain.value_objects import NotificationMessageType
from app.modules.notifications.tests.test_application import (
    TEST_USER_ID,
    InMemoryNotificationRepository,
)
from tests.support.unit_of_work import FakeUnitOfWork

MISSING_NOTIFICATION_ID = UUID("00000000-0000-0000-0000-000000000999")


async def test_delete_notification_commits_after_deleting_owned_notification() -> None:
    # Given: 현재 사용자가 소유한 알림과 삭제 use case가 준비되어 있다.
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
    unit_of_work = FakeUnitOfWork()
    use_case = DeleteNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 현재 사용자의 알림 삭제를 실행한다.
    await use_case.execute(
        DeleteNotificationCommand(
            user_id=TEST_USER_ID,
            notification_id=notification.id,
        )
    )

    # Then: 알림이 삭제되고 commit은 한 번 수행된다.
    assert notification.id not in repository.notifications
    assert unit_of_work.commit_count == 1


async def test_delete_notification_raises_not_found_without_commit_when_missing() -> None:
    # Given: 현재 사용자에게 없는 알림 ID와 삭제 use case가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = DeleteNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 없는 알림 삭제를 실행한다.
    with pytest.raises(NotFoundError, match=r"알림을 찾을 수 없습니다\."):
        await use_case.execute(
            DeleteNotificationCommand(
                user_id=TEST_USER_ID,
                notification_id=MISSING_NOTIFICATION_ID,
            )
        )

    # Then: 404 의미의 예외가 발생하고 commit은 수행되지 않는다.
    assert unit_of_work.commit_count == 0

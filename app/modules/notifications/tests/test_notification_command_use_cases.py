from uuid import uuid4

import pytest

from app.core.domain.exceptions import NotFoundError, ValidationError
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.use_case import (
    CreateNotificationCommandUseCase,
)
from app.modules.notifications.application.commands.mark_notification_read.command import (
    MarkNotificationReadCommand,
)
from app.modules.notifications.application.commands.mark_notification_read.use_case import (
    MarkNotificationReadCommandUseCase,
)
from app.modules.notifications.application.commands.update_notification_settings.command import (
    UpdateNotificationSettingsCommand,
)
from app.modules.notifications.application.commands.update_notification_settings.use_case import (
    UpdateNotificationSettingsCommandUseCase,
)
from app.modules.notifications.domain.model import NotificationSettings, UserNotification
from app.modules.notifications.domain.value_objects import (
    NotificationKind,
    NotificationTargetType,
)
from app.modules.notifications.tests.test_application import (
    CREATED_AT,
    OTHER_USER_ID,
    READ_AT,
    TEST_USER_ID,
    InMemoryNotificationRepository,
)
from tests.support.unit_of_work import FakeUnitOfWork


async def test_create_notification_commits_once_and_returns_expected_result() -> None:
    # Given: 알림 생성 use case와 in-memory repository가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = CreateNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        clock=lambda: CREATED_AT,
    )

    # When: 현재 사용자에게 알림을 생성한다.
    result = await use_case.execute(
        CreateNotificationCommand(
            user_id=TEST_USER_ID,
            kind=NotificationKind.REGISTRATION_PROMPT,
            message="영수증을 등록해 보세요.",
            target_type=NotificationTargetType.RECEIPT_UPLOAD,
        )
    )

    # Then: 저장된 알림 결과를 반환하고 commit은 한 번만 수행된다.
    saved = repository.notifications[result.notification_id]
    assert unit_of_work.commit_count == 1
    assert repository.create_count == 1
    assert saved.user_id == TEST_USER_ID
    assert result.kind == NotificationKind.REGISTRATION_PROMPT
    assert result.message == "영수증을 등록해 보세요."
    assert result.target_type == NotificationTargetType.RECEIPT_UPLOAD
    assert result.target_id is None
    assert result.read_at is None


async def test_create_notification_propagates_validation_without_commit() -> None:
    # Given: 알림 생성 use case가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = CreateNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        clock=lambda: CREATED_AT,
    )

    # When: 도메인 규칙을 위반한 message로 알림 생성을 시도한다.
    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            CreateNotificationCommand(
                user_id=TEST_USER_ID,
                kind=NotificationKind.BENEFIT,
                message=" 앞뒤 공백은 허용되지 않습니다.",
            )
        )

    # Then: validation error가 전파되고 저장/commit은 수행되지 않는다.
    assert [detail.field for detail in error.value.details] == ["message"]
    assert repository.notifications == {}
    assert repository.create_count == 0
    assert unit_of_work.commit_count == 0


async def test_mark_notification_read_commits_once_and_returns_expected_result() -> None:
    # Given: 현재 사용자에게 읽지 않은 알림이 있다.
    repository = InMemoryNotificationRepository()
    notification = UserNotification.create(
        user_id=TEST_USER_ID,
        kind=NotificationKind.WARRANTY_NOTICE,
        message="보증 만료가 다가옵니다.",
        created_at=CREATED_AT,
    )
    repository.notifications[notification.id] = notification
    unit_of_work = FakeUnitOfWork()
    use_case = MarkNotificationReadCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        clock=lambda: READ_AT,
    )

    # When: 현재 사용자의 알림을 읽음 처리한다.
    result = await use_case.execute(
        MarkNotificationReadCommand(
            user_id=TEST_USER_ID,
            notification_id=notification.id,
        )
    )

    # Then: 읽음 시각이 반영되고 commit은 한 번만 수행된다.
    saved = repository.notifications[notification.id]
    assert unit_of_work.commit_count == 1
    assert repository.mark_read_count == 1
    assert result.notification_id == notification.id
    assert result.kind == NotificationKind.WARRANTY_NOTICE
    assert result.message == "보증 만료가 다가옵니다."
    assert result.read_at == READ_AT
    assert saved.read_at == READ_AT


async def test_mark_missing_notification_raises_not_found_without_commit() -> None:
    # Given: 현재 사용자에게 없는 알림 ID가 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = MarkNotificationReadCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        clock=lambda: READ_AT,
    )

    # When: 없는 알림을 읽음 처리한다.
    with pytest.raises(NotFoundError):
        await use_case.execute(
            MarkNotificationReadCommand(user_id=TEST_USER_ID, notification_id=uuid4())
        )

    # Then: NotFoundError가 전파되고 commit은 수행되지 않는다.
    assert unit_of_work.commit_count == 0


async def test_mark_foreign_notification_raises_not_found_without_commit() -> None:
    # Given: 다른 사용자에게만 속한 알림이 있다.
    repository = InMemoryNotificationRepository()
    foreign_notification = UserNotification.create(
        user_id=OTHER_USER_ID,
        kind=NotificationKind.BENEFIT,
        message="다른 사용자 알림입니다.",
        created_at=CREATED_AT,
    )
    repository.notifications[foreign_notification.id] = foreign_notification
    unit_of_work = FakeUnitOfWork()
    use_case = MarkNotificationReadCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        clock=lambda: READ_AT,
    )

    # When: 현재 사용자가 다른 사용자의 알림을 읽음 처리한다.
    with pytest.raises(NotFoundError):
        await use_case.execute(
            MarkNotificationReadCommand(
                user_id=TEST_USER_ID,
                notification_id=foreign_notification.id,
            )
        )

    # Then: 존재 여부를 숨기며 commit은 수행되지 않는다.
    assert repository.notifications[foreign_notification.id].read_at is None
    assert unit_of_work.commit_count == 0


async def test_update_settings_partial_update_preserves_omitted_values_and_commits_once() -> None:
    # Given: 기존 NotificationSettings에서 마케팅 동의만 켜져 있다.
    repository = InMemoryNotificationRepository()
    repository.settings[TEST_USER_ID] = NotificationSettings.create(
        user_id=TEST_USER_ID,
        push_enabled=True,
        marketing_consent=True,
    )
    unit_of_work = FakeUnitOfWork()
    use_case = UpdateNotificationSettingsCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: pushEnabled만 부분 수정한다.
    result = await use_case.execute(
        UpdateNotificationSettingsCommand(
            user_id=TEST_USER_ID,
            push_enabled=False,
        )
    )

    # Then: 생략된 marketingConsent는 보존되고 commit은 한 번만 수행된다.
    settings = repository.settings[TEST_USER_ID]
    assert result.push_enabled is False
    assert result.marketing_consent is True
    assert settings.push_enabled is False
    assert settings.marketing_consent is True
    assert repository.update_settings_count == 1
    assert unit_of_work.commit_count == 1

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.domain.exceptions import ExternalServiceError, NotFoundError, ValidationError
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.use_case import (
    PUSH_TITLES,
    CreateNotificationCommandUseCase,
)
from app.modules.notifications.application.commands.delete_stale_push_tokens.command import (
    DeleteStalePushTokensCommand,
)
from app.modules.notifications.application.commands.delete_stale_push_tokens.use_case import (
    DeleteStalePushTokensCommandUseCase,
)
from app.modules.notifications.application.commands.delete_user_push_tokens.command import (
    DeleteUserPushTokensCommand,
)
from app.modules.notifications.application.commands.delete_user_push_tokens.use_case import (
    DeleteUserPushTokensCommandUseCase,
)
from app.modules.notifications.application.commands.mark_notification_read.command import (
    MarkNotificationReadCommand,
)
from app.modules.notifications.application.commands.mark_notification_read.use_case import (
    MarkNotificationReadCommandUseCase,
)
from app.modules.notifications.application.commands.register_device_token.command import (
    RegisterDeviceTokenCommand,
)
from app.modules.notifications.application.commands.register_device_token.use_case import (
    RegisterDeviceTokenCommandUseCase,
)
from app.modules.notifications.application.commands.unregister_device_token.command import (
    UnregisterDeviceTokenCommand,
)
from app.modules.notifications.application.commands.unregister_device_token.use_case import (
    UnregisterDeviceTokenCommandUseCase,
)
from app.modules.notifications.application.commands.update_notification_settings.command import (
    UpdateNotificationSettingsCommand,
)
from app.modules.notifications.application.commands.update_notification_settings.use_case import (
    UpdateNotificationSettingsCommandUseCase,
)
from app.modules.notifications.application.ports.push_sender import PushSendReport
from app.modules.notifications.domain.model import (
    NotificationSettings,
    UserNotification,
    UserPushToken,
)
from app.modules.notifications.domain.value_objects import (
    DevicePlatform,
    NotificationKind,
    NotificationTargetType,
)
from app.modules.notifications.tests.test_application import (
    CREATED_AT,
    OTHER_USER_ID,
    READ_AT,
    TEST_USER_ID,
    FakePushSender,
    InMemoryNotificationRepository,
    InMemoryPushTokenRepository,
)
from tests.support.unit_of_work import FakeUnitOfWork


def _create_use_case(
    *,
    repository: InMemoryNotificationRepository,
    push_token_repository: InMemoryPushTokenRepository,
    push_sender: FakePushSender,
    unit_of_work: FakeUnitOfWork,
) -> CreateNotificationCommandUseCase:
    return CreateNotificationCommandUseCase(
        notification_repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
        clock=lambda: CREATED_AT,
    )


async def test_create_notification_commits_once_and_returns_expected_result() -> None:
    # Given: 알림 생성 use case와 in-memory repository가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    push_sender = FakePushSender()
    unit_of_work = FakeUnitOfWork()
    use_case = _create_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
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
    # 등록된 디바이스가 없으므로 발송은 시도되지 않는다.
    assert push_sender.calls == []


async def test_create_notification_propagates_validation_without_commit() -> None:
    # Given: 알림 생성 use case가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    push_sender = FakePushSender()
    unit_of_work = FakeUnitOfWork()
    use_case = _create_use_case(
        repository=repository,
        push_token_repository=InMemoryPushTokenRepository(),
        push_sender=push_sender,
        unit_of_work=unit_of_work,
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

    # Then: validation error가 전파되고 저장/commit/발송은 수행되지 않는다.
    assert [detail.field for detail in error.value.details] == ["message"]
    assert repository.notifications == {}
    assert repository.create_count == 0
    assert unit_of_work.commit_count == 0
    assert push_sender.calls == []


def test_push_titles_cover_every_notification_kind() -> None:
    # Then: 새 NotificationKind가 추가되면 푸시 제목도 함께 정의하도록 강제한다.
    assert set(PUSH_TITLES) == set(NotificationKind)


async def test_create_notification_sends_push_to_registered_devices() -> None:
    # Given: 현재 사용자에게 등록된 디바이스 2대가 있다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        device_id="device-1",
        fcm_token="fcm-token-1",
        platform=DevicePlatform.ANDROID,
    )
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        device_id="device-2",
        fcm_token="fcm-token-2",
        platform=DevicePlatform.IOS,
    )
    await push_token_repository.register(
        user_id=OTHER_USER_ID,
        device_id="device-9",
        fcm_token="fcm-token-9",
        platform=DevicePlatform.IOS,
    )
    push_sender = FakePushSender()
    unit_of_work = FakeUnitOfWork()
    use_case = _create_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
    )

    # When: 현재 사용자에게 알림을 생성한다.
    result = await use_case.execute(
        CreateNotificationCommand(
            user_id=TEST_USER_ID,
            kind=NotificationKind.WARRANTY_RISK,
            message="보증 만료가 임박했습니다.",
        )
    )

    # Then: 현재 사용자의 토큰에만 제목/본문/데이터가 채워진 푸시가 한 번 발송된다.
    assert len(push_sender.calls) == 1
    sent_tokens, sent_message = push_sender.calls[0]
    assert {token.fcm_token.value for token in sent_tokens} == {"fcm-token-1", "fcm-token-2"}
    assert sent_message.title == "보증 만료 임박"
    assert sent_message.body == "보증 만료가 임박했습니다."
    assert sent_message.data == {
        "notificationId": str(result.notification_id),
        "kind": "warranty_risk",
        "targetType": "none",
    }
    assert unit_of_work.commit_count == 1


async def test_create_notification_skips_push_when_push_disabled() -> None:
    # Given: 사용자가 푸시 수신을 꺼 두었고 등록된 디바이스가 있다.
    repository = InMemoryNotificationRepository()
    repository.settings[TEST_USER_ID] = NotificationSettings.create(
        user_id=TEST_USER_ID,
        push_enabled=False,
    )
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        device_id="device-1",
        fcm_token="fcm-token-1",
        platform=DevicePlatform.ANDROID,
    )
    push_sender = FakePushSender()
    unit_of_work = FakeUnitOfWork()
    use_case = _create_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
    )

    # When: 알림을 생성한다.
    await use_case.execute(
        CreateNotificationCommand(
            user_id=TEST_USER_ID,
            kind=NotificationKind.BENEFIT,
            message="이번 달 혜택을 확인해 보세요.",
        )
    )

    # Then: 알림은 저장되지만 발송은 시도되지 않는다.
    assert repository.create_count == 1
    assert unit_of_work.commit_count == 1
    assert push_sender.calls == []


async def test_create_notification_deletes_invalid_tokens_and_commits_again() -> None:
    # Given: 등록 디바이스 중 하나의 토큰이 FCM에서 무효 판정을 받는다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        device_id="device-1",
        fcm_token="fcm-token-dead",
        platform=DevicePlatform.ANDROID,
    )
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        device_id="device-2",
        fcm_token="fcm-token-live",
        platform=DevicePlatform.IOS,
    )
    push_sender = FakePushSender(report=PushSendReport(invalid_tokens=("fcm-token-dead",)))
    unit_of_work = FakeUnitOfWork()
    use_case = _create_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
    )

    # When: 알림을 생성한다.
    await use_case.execute(
        CreateNotificationCommand(
            user_id=TEST_USER_ID,
            kind=NotificationKind.BENEFIT,
            message="이번 달 혜택을 확인해 보세요.",
        )
    )

    # Then: 무효 토큰만 삭제되고 정리를 위한 commit이 한 번 더 수행된다.
    assert push_token_repository.delete_by_fcm_tokens_count == 1
    assert (TEST_USER_ID, "device-1") not in push_token_repository.tokens
    assert (TEST_USER_ID, "device-2") in push_token_repository.tokens
    assert unit_of_work.commit_count == 2


async def test_create_notification_survives_push_send_failure() -> None:
    # Given: 푸시 발송이 외부 서비스 장애로 실패한다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        device_id="device-1",
        fcm_token="fcm-token-1",
        platform=DevicePlatform.ANDROID,
    )
    push_sender = FakePushSender(error=ExternalServiceError("푸시 발송에 실패했습니다."))
    unit_of_work = FakeUnitOfWork()
    use_case = _create_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
    )

    # When: 알림을 생성한다.
    result = await use_case.execute(
        CreateNotificationCommand(
            user_id=TEST_USER_ID,
            kind=NotificationKind.BENEFIT,
            message="이번 달 혜택을 확인해 보세요.",
        )
    )

    # Then: 발송 실패에도 알림 생성은 성공으로 남고 토큰은 유지된다.
    assert result.notification_id in repository.notifications
    assert unit_of_work.commit_count == 1
    assert len(push_sender.calls) == 1
    assert (TEST_USER_ID, "device-1") in push_token_repository.tokens


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


async def test_register_device_token_commits_once_and_returns_saved_token() -> None:
    # Given: push token 등록 use case가 준비되어 있다.
    repository = InMemoryPushTokenRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = RegisterDeviceTokenCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 유효한 디바이스 토큰을 등록한다.
    saved = await use_case.execute(
        RegisterDeviceTokenCommand(
            user_id=TEST_USER_ID,
            device_id="device-1",
            fcm_token="fcm-token-1",
            platform=DevicePlatform.ANDROID,
        )
    )

    # Then: repository에 위임되고 commit은 한 번만 수행된다.
    assert repository.register_count == 1
    assert unit_of_work.commit_count == 1
    assert saved.user_id == TEST_USER_ID
    assert saved.device_id.value == "device-1"
    assert saved.fcm_token.value == "fcm-token-1"
    assert saved.platform == DevicePlatform.ANDROID


async def test_register_device_token_with_oversized_token_raises_without_commit() -> None:
    # Given: push token 등록 use case가 준비되어 있다.
    repository = InMemoryPushTokenRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = RegisterDeviceTokenCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 513자 fcm_token으로 등록을 시도한다.
    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            RegisterDeviceTokenCommand(
                user_id=TEST_USER_ID,
                device_id="device-1",
                fcm_token="a" * 513,
                platform=DevicePlatform.IOS,
            )
        )

    # Then: DB에 닿기 전에 검증에서 거부되고 commit은 수행되지 않는다.
    assert [detail.field for detail in error.value.details] == ["fcmToken"]
    assert repository.register_count == 0
    assert unit_of_work.commit_count == 0


async def test_unregister_device_token_commits_once() -> None:
    # Given: 등록된 디바이스 토큰이 있다.
    repository = InMemoryPushTokenRepository()
    await repository.register(
        user_id=TEST_USER_ID,
        device_id="device-1",
        fcm_token="fcm-token-1",
        platform=DevicePlatform.ANDROID,
    )
    unit_of_work = FakeUnitOfWork()
    use_case = UnregisterDeviceTokenCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 등록된 디바이스를 해제한다.
    await use_case.execute(UnregisterDeviceTokenCommand(user_id=TEST_USER_ID, device_id="device-1"))

    # Then: repository에 위임되고 commit은 한 번만 수행된다.
    assert repository.unregister_count == 1
    assert unit_of_work.commit_count == 1
    assert (TEST_USER_ID, "device-1") not in repository.tokens


async def test_delete_stale_push_tokens_removes_only_tokens_older_than_cutoff() -> None:
    # Given: 기준 시각보다 오래된 토큰과 최근에 갱신된 토큰이 있다.
    repository = InMemoryPushTokenRepository()
    stale_token = UserPushToken.create(
        user_id=TEST_USER_ID,
        device_id="stale-device",
        fcm_token="fcm-token-stale",
        platform=DevicePlatform.ANDROID,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )
    fresh_token = UserPushToken.create(
        user_id=TEST_USER_ID,
        device_id="fresh-device",
        fcm_token="fcm-token-fresh",
        platform=DevicePlatform.IOS,
        created_at=READ_AT,
        updated_at=READ_AT,
    )
    repository.tokens[(TEST_USER_ID, "stale-device")] = stale_token
    repository.tokens[(TEST_USER_ID, "fresh-device")] = fresh_token
    unit_of_work = FakeUnitOfWork()
    use_case = DeleteStalePushTokensCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: CREATED_AT과 READ_AT 사이 시각을 기준으로 정리한다.
    result = await use_case.execute(
        DeleteStalePushTokensCommand(older_than=datetime(2026, 6, 28, 3, 0, tzinfo=UTC))
    )

    # Then: 기준보다 오래된 토큰만 삭제되고 삭제 건수가 보고되며 commit은 한 번 수행된다.
    assert result.deleted_count == 1
    assert repository.delete_stale_count == 1
    assert set(repository.tokens) == {(TEST_USER_ID, "fresh-device")}
    assert unit_of_work.commit_count == 1


async def test_delete_stale_push_tokens_without_stale_tokens_reports_zero() -> None:
    # Given: 정리 대상이 없는 저장소가 있다.
    repository = InMemoryPushTokenRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = DeleteStalePushTokensCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 정리를 실행한다.
    result = await use_case.execute(
        DeleteStalePushTokensCommand(older_than=datetime(2026, 6, 28, 3, 0, tzinfo=UTC))
    )

    # Then: 0건 삭제를 보고하고 멱등하게 commit이 한 번 수행된다.
    assert result.deleted_count == 0
    assert unit_of_work.commit_count == 1


async def test_delete_user_push_tokens_removes_only_target_user_tokens() -> None:
    # Given: 두 사용자에게 등록된 디바이스 토큰이 있다.
    repository = InMemoryPushTokenRepository()
    await repository.register(
        user_id=TEST_USER_ID,
        device_id="device-1",
        fcm_token="fcm-token-1",
        platform=DevicePlatform.ANDROID,
    )
    await repository.register(
        user_id=TEST_USER_ID,
        device_id="device-2",
        fcm_token="fcm-token-2",
        platform=DevicePlatform.IOS,
    )
    await repository.register(
        user_id=OTHER_USER_ID,
        device_id="device-9",
        fcm_token="fcm-token-9",
        platform=DevicePlatform.IOS,
    )
    unit_of_work = FakeUnitOfWork()
    use_case = DeleteUserPushTokensCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 탈퇴 사용자의 토큰을 전부 삭제한다.
    await use_case.execute(DeleteUserPushTokensCommand(user_id=TEST_USER_ID))

    # Then: 해당 사용자 토큰만 사라지고 commit은 한 번만 수행된다.
    assert repository.delete_by_user_id_count == 1
    assert unit_of_work.commit_count == 1
    assert set(repository.tokens) == {(OTHER_USER_ID, "device-9")}


async def test_delete_user_push_tokens_without_tokens_still_commits_idempotently() -> None:
    # Given: 등록된 토큰이 없는 사용자가 있다.
    repository = InMemoryPushTokenRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = DeleteUserPushTokensCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 토큰 삭제를 실행한다.
    await use_case.execute(DeleteUserPushTokensCommand(user_id=TEST_USER_ID))

    # Then: 예외 없이 멱등하게 commit이 한 번 수행된다.
    assert repository.delete_by_user_id_count == 1
    assert unit_of_work.commit_count == 1


async def test_unregister_missing_device_token_still_commits_idempotently() -> None:
    # Given: 등록되지 않은 디바이스 토큰이 있다.
    repository = InMemoryPushTokenRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = UnregisterDeviceTokenCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 존재하지 않는 device_id를 해제한다.
    await use_case.execute(
        UnregisterDeviceTokenCommand(user_id=TEST_USER_ID, device_id="missing-device")
    )

    # Then: 예외 없이 멱등하게 commit이 한 번 수행된다.
    assert repository.unregister_count == 1
    assert unit_of_work.commit_count == 1

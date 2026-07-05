from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.domain.exceptions import NotFoundError, ValidationError
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.use_case import (
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
from app.modules.notifications.application.commands.send_notification_push.command import (
    SendNotificationPushCommand,
)
from app.modules.notifications.application.commands.send_notification_push.use_case import (
    SendNotificationPushCommandUseCase,
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
from app.modules.notifications.domain.events import NotificationCreated
from app.modules.notifications.domain.model import (
    NotificationSettings,
    UserNotification,
    UserPushToken,
)
from app.modules.notifications.domain.value_objects import (
    DevicePlatform,
    NotificationMessageType,
)
from app.modules.notifications.tests.test_application import (
    CREATED_AT,
    OTHER_USER_ID,
    READ_AT,
    TEST_USER_ID,
    FakeEventPublisher,
    FakePushSender,
    InMemoryNotificationRepository,
    InMemoryPushTokenRepository,
)
from tests.support.unit_of_work import FakeUnitOfWork


def _send_push_use_case(
    *,
    repository: InMemoryNotificationRepository,
    push_token_repository: InMemoryPushTokenRepository,
    push_sender: FakePushSender,
    unit_of_work: FakeUnitOfWork,
) -> SendNotificationPushCommandUseCase:
    return SendNotificationPushCommandUseCase(
        notification_repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
    )


def _send_push_command(
    *,
    message_type: NotificationMessageType = NotificationMessageType.TRANSACTIONAL,
    kind: str,
    title: str,
    message: str,
) -> SendNotificationPushCommand:
    return SendNotificationPushCommand(
        user_id=TEST_USER_ID,
        notification_id=uuid4(),
        message_type=message_type,
        kind=kind,
        title=title,
        message=message,
        resource_type=None,
        resource_id=None,
    )


async def test_create_notification_commits_once_and_returns_expected_result() -> None:
    # Given: 알림 생성 use case와 in-memory repository가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    event_publisher = FakeEventPublisher()
    use_case = CreateNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        event_publisher=event_publisher,
        clock=lambda: CREATED_AT,
    )

    # When: 현재 사용자에게 알림을 생성한다.
    receipt_id = uuid4()
    result = await use_case.execute(
        CreateNotificationCommand(
            user_id=TEST_USER_ID,
            message_type=NotificationMessageType.TRANSACTIONAL,
            kind="registration_prompt",
            title="영수증 등록 안내",
            message="영수증을 등록해 보세요.",
            resource_type="receipt",
            resource_id=receipt_id,
            metadata={"subCategory": "receiptUpload"},
        )
    )

    # Then: 저장된 알림 결과를 반환하고 commit은 한 번만 수행된다.
    saved = repository.notifications[result.notification_id]
    assert unit_of_work.commit_count == 1
    assert repository.create_count == 1
    assert saved.user_id == TEST_USER_ID
    assert result.message_type == NotificationMessageType.TRANSACTIONAL
    assert result.kind == "registration_prompt"
    assert result.title == "영수증 등록 안내"
    assert result.message == "영수증을 등록해 보세요."
    assert result.resource_type == "receipt"
    assert result.resource_id == receipt_id
    assert result.metadata == {"subCategory": "receiptUpload"}
    assert result.read_at is None

    # And: NotificationCreated 이벤트가 정확한 payload로 정확히 한 번 발행된다.
    assert len(event_publisher.published) == 1
    published_event = event_publisher.published[0]
    assert isinstance(published_event, NotificationCreated)
    assert published_event.notification_id == result.notification_id
    assert published_event.user_id == TEST_USER_ID
    assert published_event.message_type == NotificationMessageType.TRANSACTIONAL
    assert published_event.kind == "registration_prompt"
    assert published_event.title == "영수증 등록 안내"
    assert published_event.message == "영수증을 등록해 보세요."
    assert published_event.resource_type == "receipt"
    assert published_event.resource_id == receipt_id


def test_restore_does_not_record_creation_event() -> None:
    # Given/When: 저장소 레코드 복원 전용 팩토리로 알림을 재구성한다.
    restored = UserNotification.restore(
        notification_id=uuid4(),
        user_id=TEST_USER_ID,
        message_type=NotificationMessageType.TRANSACTIONAL,
        kind="warranty_risk",
        title="보증 만료 임박",
        message="냉장고 보증이 30일 뒤 만료돼요.",
        resource_type="receipt",
        resource_id=uuid4(),
        metadata={"subCategory": "warranty"},
        created_at=CREATED_AT,
        read_at=None,
    )

    # Then: 복원된 알림에는 생성 이벤트가 쌓이지 않는다(푸시 재발행 방지).
    assert restored.pull_events() == []
    # And: metadata는 그대로 보존된다.
    assert restored.metadata.value == {"subCategory": "warranty"}


async def test_create_notification_succeeds_when_event_publish_fails() -> None:
    # Given: publish가 항상 실패하는 event publisher가 주입되어 있다.
    class FailingEventPublisher(FakeEventPublisher):
        async def publish(self, events: object) -> None:
            raise RuntimeError("publish 실패")

    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = CreateNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        event_publisher=FailingEventPublisher(),
        clock=lambda: CREATED_AT,
    )

    # When: 알림을 생성한다.
    result = await use_case.execute(
        CreateNotificationCommand(
            user_id=TEST_USER_ID,
            message_type=NotificationMessageType.TRANSACTIONAL,
            kind="warranty_risk",
            title="보증 만료 임박",
            message="냉장고 보증이 30일 뒤 만료돼요.",
        )
    )

    # Then: 알림은 이미 커밋됐으므로 발행 실패가 생성 결과를 깨지 않는다(best-effort).
    assert unit_of_work.commit_count == 1
    assert result.notification_id in repository.notifications


async def test_create_notification_propagates_validation_without_commit() -> None:
    # Given: 알림 생성 use case가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = CreateNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        event_publisher=FakeEventPublisher(),
        clock=lambda: CREATED_AT,
    )

    # When: 도메인 규칙을 위반한 message로 알림 생성을 시도한다.
    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            CreateNotificationCommand(
                user_id=TEST_USER_ID,
                message_type=NotificationMessageType.MARKETING,
                kind="benefit",
                title="혜택 안내",
                message=" 앞뒤 공백은 허용되지 않습니다.",
            )
        )

    # Then: validation error가 전파되고 저장/commit은 수행되지 않는다.
    assert [detail.field for detail in error.value.details] == ["message"]
    assert repository.notifications == {}
    assert repository.create_count == 0
    assert unit_of_work.commit_count == 0


async def test_create_notification_rejects_resource_pair_mismatch_without_commit() -> None:
    # Given: 알림 생성 use case가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = CreateNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        event_publisher=FakeEventPublisher(),
        clock=lambda: CREATED_AT,
    )

    # When: resourceType만 채우고 resourceId는 생략한다.
    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            CreateNotificationCommand(
                user_id=TEST_USER_ID,
                message_type=NotificationMessageType.TRANSACTIONAL,
                kind="registration_prompt",
                title="영수증 등록 안내",
                message="영수증을 등록해 보세요.",
                resource_type="receipt",
                resource_id=None,
            )
        )

    # Then: resource 필드에 대한 validation error가 전파되고 commit은 수행되지 않는다.
    assert [detail.field for detail in error.value.details] == ["resource"]
    assert unit_of_work.commit_count == 0


async def test_create_notification_rejects_oversized_kind_without_commit() -> None:
    # Given: 알림 생성 use case가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = CreateNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        event_publisher=FakeEventPublisher(),
        clock=lambda: CREATED_AT,
    )

    # When: 51자 kind로 알림 생성을 시도한다.
    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            CreateNotificationCommand(
                user_id=TEST_USER_ID,
                message_type=NotificationMessageType.TRANSACTIONAL,
                kind="a" * 51,
                title="제목",
                message="문구",
            )
        )

    # Then: kind 필드 validation error가 전파되고 commit은 수행되지 않는다.
    assert [detail.field for detail in error.value.details] == ["kind"]
    assert unit_of_work.commit_count == 0


async def test_create_notification_rejects_oversized_title_without_commit() -> None:
    # Given: 알림 생성 use case가 준비되어 있다.
    repository = InMemoryNotificationRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = CreateNotificationCommandUseCase(
        notification_repository=repository,
        unit_of_work=unit_of_work,
        event_publisher=FakeEventPublisher(),
        clock=lambda: CREATED_AT,
    )

    # When: 101자 title로 알림 생성을 시도한다.
    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            CreateNotificationCommand(
                user_id=TEST_USER_ID,
                message_type=NotificationMessageType.TRANSACTIONAL,
                kind="benefit",
                title="a" * 101,
                message="문구",
            )
        )

    # Then: title 필드 validation error가 전파되고 commit은 수행되지 않는다.
    assert [detail.field for detail in error.value.details] == ["title"]
    assert unit_of_work.commit_count == 0


async def test_send_notification_push_sends_to_registered_devices() -> None:
    # Given: 현재 사용자에게 등록된 디바이스 2대가 있다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-2",
        platform=DevicePlatform.IOS,
    )
    await push_token_repository.register(
        user_id=OTHER_USER_ID,
        token="token-9",
        platform=DevicePlatform.IOS,
    )
    push_sender = FakePushSender()
    unit_of_work = FakeUnitOfWork()
    use_case = _send_push_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
    )
    command = _send_push_command(
        kind="warranty_risk",
        title="보증 만료 임박",
        message="보증 만료가 임박했습니다.",
    )

    # When: 알림 푸시 발송을 실행한다.
    await use_case.execute(command)

    # Then: 현재 사용자의 등록에만 제목/본문/데이터가 채워진 푸시가 한 번 발송된다.
    assert len(push_sender.calls) == 1
    sent_tokens, sent_message = push_sender.calls[0]
    assert {token.token.value for token in sent_tokens} == {"token-1", "token-2"}
    assert sent_message.title == "보증 만료 임박"
    assert sent_message.body == "보증 만료가 임박했습니다."
    assert sent_message.data == {
        "notificationId": str(command.notification_id),
        "messageType": "transactional",
        "kind": "warranty_risk",
    }
    assert unit_of_work.commit_count == 0


async def test_send_notification_push_includes_resource_fields_when_present() -> None:
    # Given: 리소스 참조가 있는 알림 발송 커맨드가 있다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    push_sender = FakePushSender()
    unit_of_work = FakeUnitOfWork()
    use_case = _send_push_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
    )
    receipt_id = uuid4()
    command = SendNotificationPushCommand(
        user_id=TEST_USER_ID,
        notification_id=uuid4(),
        message_type=NotificationMessageType.TRANSACTIONAL,
        kind="warranty_risk",
        title="보증 만료 임박",
        message="보증 만료가 임박했습니다.",
        resource_type="receipt",
        resource_id=receipt_id,
    )

    # When: 알림 푸시 발송을 실행한다.
    await use_case.execute(command)

    # Then: 발송 데이터에 resourceType/resourceId가 포함된다.
    _, sent_message = push_sender.calls[0]
    assert sent_message.data == {
        "notificationId": str(command.notification_id),
        "messageType": "transactional",
        "kind": "warranty_risk",
        "resourceType": "receipt",
        "resourceId": str(receipt_id),
    }


async def test_send_notification_push_skips_when_push_disabled() -> None:
    # Given: 사용자가 푸시 수신을 꺼 두었고 등록된 디바이스가 있다.
    repository = InMemoryNotificationRepository()
    repository.settings[TEST_USER_ID] = NotificationSettings.create(
        user_id=TEST_USER_ID,
        push_enabled=False,
    )
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    push_sender = FakePushSender()
    use_case = _send_push_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=FakeUnitOfWork(),
    )

    # When: 알림 푸시 발송을 실행한다.
    await use_case.execute(
        _send_push_command(
            message_type=NotificationMessageType.MARKETING,
            kind="benefit",
            title="혜택 안내",
            message="이번 달 혜택을 확인해 보세요.",
        )
    )

    # Then: 발송은 시도되지 않는다.
    assert push_sender.calls == []


async def test_send_notification_push_deletes_invalid_registrations_and_commits() -> None:
    # Given: 등록 디바이스 중 하나가 FCM에서 무효 판정을 받는다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-dead",
        platform=DevicePlatform.ANDROID,
    )
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-live",
        platform=DevicePlatform.IOS,
    )
    push_sender = FakePushSender(report=PushSendReport(invalid_tokens=("token-dead",)))
    unit_of_work = FakeUnitOfWork()
    use_case = _send_push_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=unit_of_work,
    )

    # When: 알림 푸시 발송을 실행한다.
    await use_case.execute(
        _send_push_command(
            kind="credit_prompt",
            title="크레딧 안내",
            message="분석 가능 횟수를 확인해 보세요.",
        )
    )

    # Then: 무효 등록만 삭제되고 정리를 위한 commit이 수행된다.
    assert push_token_repository.delete_by_tokens_count == 1
    assert "token-dead" not in push_token_repository.tokens
    assert "token-live" in push_token_repository.tokens
    assert unit_of_work.commit_count == 1


async def test_send_notification_push_swallows_any_send_failure() -> None:
    # Given: 푸시 발송이 예기치 못한 예외로 실패한다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    push_sender = FakePushSender(error=RuntimeError("예상하지 못한 발송 실패"))
    use_case = _send_push_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=FakeUnitOfWork(),
    )

    # When: 알림 푸시 발송을 실행한다.
    await use_case.execute(
        _send_push_command(
            kind="credit_prompt",
            title="크레딧 안내",
            message="분석 가능 횟수를 확인해 보세요.",
        )
    )

    # Then: 예외는 전파되지 않고 등록은 유지된다.
    assert len(push_sender.calls) == 1
    assert "token-1" in push_token_repository.tokens


async def test_send_marketing_push_skips_without_marketing_consent() -> None:
    # Given: push 수신은 켜져 있지만 마케팅 수신 동의는 없는 기본 상태다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    push_sender = FakePushSender()
    use_case = _send_push_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=FakeUnitOfWork(),
    )

    # When: 마케팅성(marketing) 알림 푸시 발송을 실행한다.
    await use_case.execute(
        _send_push_command(
            message_type=NotificationMessageType.MARKETING,
            kind="benefit",
            title="혜택 안내",
            message="이번 달 혜택을 확인해 보세요.",
        )
    )

    # Then: 마케팅 동의가 없어 발송은 시도되지 않는다.
    assert push_sender.calls == []


async def test_send_service_push_sends_without_marketing_consent() -> None:
    # Given: push 수신은 켜져 있지만 마케팅 수신 동의는 없는 기본 상태다.
    repository = InMemoryNotificationRepository()
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    push_sender = FakePushSender()
    use_case = _send_push_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=FakeUnitOfWork(),
    )

    # When: service 알림 푸시 발송을 실행한다.
    await use_case.execute(
        _send_push_command(
            message_type=NotificationMessageType.TRANSACTIONAL,
            kind="credit_prompt",
            title="크레딧 안내",
            message="분석 가능 횟수를 확인해 보세요.",
        )
    )

    # Then: message_type가 marketing이 아니므로 마케팅 동의 없이도 발송된다.
    assert len(push_sender.calls) == 1


async def test_send_marketing_push_sends_with_marketing_consent() -> None:
    # Given: push 수신과 마케팅 수신 동의가 모두 켜져 있다.
    repository = InMemoryNotificationRepository()
    repository.settings[TEST_USER_ID] = NotificationSettings.create(
        user_id=TEST_USER_ID,
        push_enabled=True,
        marketing_consent=True,
    )
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    push_sender = FakePushSender()
    use_case = _send_push_use_case(
        repository=repository,
        push_token_repository=push_token_repository,
        push_sender=push_sender,
        unit_of_work=FakeUnitOfWork(),
    )

    # When: 마케팅성(marketing) 알림 푸시 발송을 실행한다.
    await use_case.execute(
        _send_push_command(
            message_type=NotificationMessageType.MARKETING,
            kind="benefit",
            title="혜택 안내",
            message="이번 달 혜택을 확인해 보세요.",
        )
    )

    # Then: 발송이 수행된다.
    assert len(push_sender.calls) == 1
    _, sent_message = push_sender.calls[0]
    assert sent_message.title == "혜택 안내"


async def test_mark_notification_read_commits_once_and_returns_expected_result() -> None:
    # Given: 현재 사용자에게 읽지 않은 알림이 있다.
    repository = InMemoryNotificationRepository()
    notification = UserNotification.create(
        user_id=TEST_USER_ID,
        message_type=NotificationMessageType.TRANSACTIONAL,
        kind="warranty_notice",
        title="보증 기간 안내",
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
    assert result.message_type == NotificationMessageType.TRANSACTIONAL
    assert result.kind == "warranty_notice"
    assert result.title == "보증 기간 안내"
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
        message_type=NotificationMessageType.MARKETING,
        kind="benefit",
        title="혜택 안내",
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

    # When: 유효한 FID를 등록한다.
    saved = await use_case.execute(
        RegisterDeviceTokenCommand(
            user_id=TEST_USER_ID,
            token="token-1",
            platform=DevicePlatform.ANDROID,
        )
    )

    # Then: repository에 위임되고 commit은 한 번만 수행된다.
    assert repository.register_count == 1
    assert unit_of_work.commit_count == 1
    assert saved.user_id == TEST_USER_ID
    assert saved.token.value == "token-1"
    assert saved.platform == DevicePlatform.ANDROID


async def test_register_device_token_with_oversized_token_raises_without_commit() -> None:
    # Given: push token 등록 use case가 준비되어 있다.
    repository = InMemoryPushTokenRepository()
    unit_of_work = FakeUnitOfWork()
    use_case = RegisterDeviceTokenCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 513자 token으로 등록을 시도한다.
    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            RegisterDeviceTokenCommand(
                user_id=TEST_USER_ID,
                token="a" * 513,
                platform=DevicePlatform.IOS,
            )
        )

    # Then: DB에 닿기 전에 검증에서 거부되고 commit은 수행되지 않는다.
    assert [detail.field for detail in error.value.details] == ["token"]
    assert repository.register_count == 0
    assert unit_of_work.commit_count == 0


async def test_unregister_device_token_commits_once() -> None:
    # Given: 등록된 디바이스가 있다.
    repository = InMemoryPushTokenRepository()
    await repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    unit_of_work = FakeUnitOfWork()
    use_case = UnregisterDeviceTokenCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 등록된 디바이스를 해제한다.
    await use_case.execute(UnregisterDeviceTokenCommand(user_id=TEST_USER_ID, token="token-1"))

    # Then: repository에 위임되고 commit은 한 번만 수행된다.
    assert repository.unregister_count == 1
    assert unit_of_work.commit_count == 1
    assert "token-1" not in repository.tokens


async def test_delete_stale_push_tokens_removes_only_tokens_older_than_cutoff() -> None:
    # Given: 기준 시각보다 오래된 토큰과 최근에 갱신된 토큰이 있다.
    repository = InMemoryPushTokenRepository()
    stale_token = UserPushToken.create(
        user_id=TEST_USER_ID,
        token="token-stale",
        platform=DevicePlatform.ANDROID,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )
    fresh_token = UserPushToken.create(
        user_id=TEST_USER_ID,
        token="token-fresh",
        platform=DevicePlatform.IOS,
        created_at=READ_AT,
        updated_at=READ_AT,
    )
    repository.tokens["token-stale"] = stale_token
    repository.tokens["token-fresh"] = fresh_token
    unit_of_work = FakeUnitOfWork()
    use_case = DeleteStalePushTokensCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: CREATED_AT과 READ_AT 사이 시각을 기준으로 정리한다.
    result = await use_case.execute(
        DeleteStalePushTokensCommand(older_than=datetime(2026, 6, 28, 3, 0, tzinfo=UTC))
    )

    # Then: 기준보다 오래된 등록만 삭제되고 삭제 건수가 보고되며 commit은 한 번 수행된다.
    assert result.deleted_count == 1
    assert repository.delete_stale_count == 1
    assert set(repository.tokens) == {"token-fresh"}
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
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    await repository.register(
        user_id=TEST_USER_ID,
        token="token-2",
        platform=DevicePlatform.IOS,
    )
    await repository.register(
        user_id=OTHER_USER_ID,
        token="token-9",
        platform=DevicePlatform.IOS,
    )
    unit_of_work = FakeUnitOfWork()
    use_case = DeleteUserPushTokensCommandUseCase(
        push_token_repository=repository,
        unit_of_work=unit_of_work,
    )

    # When: 탈퇴 사용자의 토큰을 전부 삭제한다.
    await use_case.execute(DeleteUserPushTokensCommand(user_id=TEST_USER_ID))

    # Then: 해당 사용자 등록만 사라지고 commit은 한 번만 수행된다.
    assert repository.delete_by_user_id_count == 1
    assert unit_of_work.commit_count == 1
    assert set(repository.tokens) == {"token-9"}


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

    # When: 존재하지 않는 token을 해제한다.
    await use_case.execute(
        UnregisterDeviceTokenCommand(user_id=TEST_USER_ID, token="missing-token")
    )

    # Then: 예외 없이 멱등하게 commit이 한 번 수행된다.
    assert repository.unregister_count == 1
    assert unit_of_work.commit_count == 1

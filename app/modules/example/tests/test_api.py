from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.core.application.event_publisher import NoOpEventPublisher
from app.core.config.settings import Settings
from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import create_app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.dependencies import get_grant_credit_command_use_case
from app.modules.credits.domain import CreditAmount, CreditReason
from app.modules.notifications.application.commands.create_notification.use_case import (
    CreateNotificationCommandUseCase,
)
from app.modules.notifications.dependencies import (
    get_push_sender,
    get_push_token_repository,
    get_test_notification_create_use_case,
)
from app.modules.notifications.domain.value_objects import (
    DevicePlatform,
    NotificationMessageType,
)
from app.modules.notifications.tests.test_application import (
    FakePushSender,
    InMemoryNotificationRepository,
    InMemoryPushTokenRepository,
)
from tests.support.unit_of_work import FakeUnitOfWork

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000401")
TEST_CREDENTIALS_ID = UUID("00000000-0000-0000-0000-000000000402")
TEST_SESSION_ID = UUID("00000000-0000-0000-0000-000000000403")


@dataclass(slots=True)
class RecordingGrantCreditCommandUseCase:
    commands: list[GrantCreditCommand] = field(default_factory=list)

    async def execute(self, command: GrantCreditCommand) -> None:
        self.commands.append(command)


async def _authenticate_test_principal(request: Request) -> AuthenticatedPrincipal:
    principal = AuthenticatedPrincipal(
        user_id=TEST_USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )
    set_current_principal(request, principal)
    return principal


def _build_test_notification_create_use_case(
    notification_repository: InMemoryNotificationRepository,
) -> CreateNotificationCommandUseCase:
    return CreateNotificationCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=FakeUnitOfWork(),
        event_publisher=NoOpEventPublisher(),
    )


async def test_force_server_error_endpoint_returns_500_failure_envelope() -> None:
    test_app = create_app(Settings(app_name="Boat Backend"))

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.get("/api/v1/example/server-error")

    body = response.json()

    assert response.status_code == 500
    assert body["success"] is False
    assert body["status"] == 500
    assert body["data"]["message"] == "서버 내부 오류가 발생했습니다."
    assert body["data"]["path"] == "/api/v1/example/server-error"
    assert body["data"]["errors"] == []


def test_force_server_error_endpoint_is_documented_in_openapi() -> None:
    schema = create_app(Settings(app_name="Boat Backend")).openapi()
    operation = schema["paths"]["/api/v1/example/server-error"]["get"]

    assert operation["summary"] == "테스트용 500 오류 발생"
    assert operation["responses"]["500"]["description"] == "서버 내부 오류 강제 발생"


async def test_grant_ocr_test_credits_endpoint_grants_current_user_credit() -> None:
    test_app = create_app(Settings(app_name="Boat Backend"))
    recorder = RecordingGrantCreditCommandUseCase()
    test_app.dependency_overrides[authenticate_current_principal] = _authenticate_test_principal
    test_app.dependency_overrides[get_grant_credit_command_use_case] = lambda: recorder

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.post("/api/v1/example/ocr-test-credits")

    body = response.json()

    assert response.status_code == 201
    assert body == {
        "success": True,
        "status": 201,
        "data": {
            "featureKey": "ocr",
            "reason": "eventOcrAllowance",
            "grantedCount": 5,
        },
    }
    assert recorder.commands == [
        GrantCreditCommand(
            user_id=TEST_USER_ID,
            amount=CreditAmount(value=5, field_name="amount"),
            reason=CreditReason.EVENT_OCR_ALLOWANCE,
        )
    ]


def test_grant_ocr_test_credits_endpoint_is_documented_in_openapi() -> None:
    schema = create_app(Settings(app_name="Boat Backend")).openapi()
    operation = schema["paths"]["/api/v1/example/ocr-test-credits"]["post"]

    assert operation["summary"] == "임시 OCR 테스트 크레딧 발급"
    assert operation["responses"]["201"]["description"] == "OCR 테스트 크레딧 발급 성공"


async def test_send_test_push_sends_to_registered_devices() -> None:
    test_app = create_app(Settings(app_name="Boat Backend"))
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.ANDROID,
    )
    await push_token_repository.register(
        user_id=UUID("00000000-0000-0000-0000-000000000501"),
        token="token-other",
        platform=DevicePlatform.IOS,
    )
    push_sender = FakePushSender()
    notification_repository = InMemoryNotificationRepository()
    test_app.dependency_overrides[authenticate_current_principal] = _authenticate_test_principal
    test_app.dependency_overrides[get_push_token_repository] = lambda: push_token_repository
    test_app.dependency_overrides[get_push_sender] = lambda: push_sender
    test_app.dependency_overrides[get_test_notification_create_use_case] = lambda: (
        _build_test_notification_create_use_case(notification_repository)
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.post("/api/v1/example/push", json={})

    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["status"] == 200
    assert body["data"]["targetedDeviceCount"] == 1
    assert body["data"]["invalidDeviceCount"] == 0
    notification_id = UUID(body["data"]["notificationId"])
    assert len(push_sender.calls) == 1
    sent_tokens, sent_message = push_sender.calls[0]
    assert [token.token.value for token in sent_tokens] == ["token-1"]
    assert sent_message.title == "테스트 알림"
    assert sent_message.body == "푸시 연결 확인용 테스트 메시지입니다."
    assert sent_message.data == {"test": "true"}
    saved_notification = notification_repository.notifications[notification_id]
    assert saved_notification.kind.value == "test"
    assert saved_notification.message_type == NotificationMessageType.TRANSACTIONAL
    assert saved_notification.title.value == "테스트 알림"
    assert saved_notification.message.value == "푸시 연결 확인용 테스트 메시지입니다."


async def test_send_test_push_uses_custom_title_and_body() -> None:
    test_app = create_app(Settings(app_name="Boat Backend"))
    push_token_repository = InMemoryPushTokenRepository()
    await push_token_repository.register(
        user_id=TEST_USER_ID,
        token="token-1",
        platform=DevicePlatform.IOS,
    )
    push_sender = FakePushSender()
    notification_repository = InMemoryNotificationRepository()
    test_app.dependency_overrides[authenticate_current_principal] = _authenticate_test_principal
    test_app.dependency_overrides[get_push_token_repository] = lambda: push_token_repository
    test_app.dependency_overrides[get_push_sender] = lambda: push_sender
    test_app.dependency_overrides[get_test_notification_create_use_case] = lambda: (
        _build_test_notification_create_use_case(notification_repository)
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.post(
            "/api/v1/example/push",
            json={"title": "커스텀 제목", "body": "커스텀 본문"},
        )

    assert response.status_code == 200
    assert len(push_sender.calls) == 1
    _, sent_message = push_sender.calls[0]
    assert sent_message.title == "커스텀 제목"
    assert sent_message.body == "커스텀 본문"


async def test_send_test_push_without_registered_devices_reports_zero() -> None:
    test_app = create_app(Settings(app_name="Boat Backend"))
    push_sender = FakePushSender()
    notification_repository = InMemoryNotificationRepository()
    test_app.dependency_overrides[authenticate_current_principal] = _authenticate_test_principal
    test_app.dependency_overrides[get_push_token_repository] = lambda: InMemoryPushTokenRepository()
    test_app.dependency_overrides[get_push_sender] = lambda: push_sender
    test_app.dependency_overrides[get_test_notification_create_use_case] = lambda: (
        _build_test_notification_create_use_case(notification_repository)
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.post("/api/v1/example/push", json={})

    body = response.json()

    assert response.status_code == 200
    assert body["data"]["targetedDeviceCount"] == 0
    assert body["data"]["invalidDeviceCount"] == 0
    assert UUID(body["data"]["notificationId"]) in notification_repository.notifications
    assert push_sender.calls == []


async def test_send_test_push_requires_authentication() -> None:
    test_app = create_app(Settings(app_name="Boat Backend"))

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as test_client:
        response = await test_client.post("/api/v1/example/push", json={})

    body = response.json()

    assert response.status_code == 401
    assert body["success"] is False


def test_send_test_push_endpoint_is_documented_in_openapi() -> None:
    schema = create_app(Settings(app_name="Boat Backend")).openapi()
    operation = schema["paths"]["/api/v1/example/push"]["post"]

    assert operation["summary"] == "테스트 푸시 발송"

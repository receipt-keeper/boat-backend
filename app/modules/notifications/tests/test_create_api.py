from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications.application.ports.push_sender import PushSendReport
from app.modules.notifications.dependencies import get_push_sender
from app.modules.notifications.infrastructure.persistence import orm
from app.modules.notifications.tests.conftest import (
    TEST_USER_ID,
    notification_api_client,
)
from app.modules.notifications.tests.test_application import FakePushSender


async def test_create_notification_returns_created_common_response(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "kind": "registration_prompt",
        "message": "영수증을 등록해 보세요.",
        "targetType": "receiptUpload",
        "targetId": None,
    }

    async with notification_api_client(postgres_session_factory) as client:
        response = await client.post("/api/v1/notifications", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["success"] is True
    assert body["status"] == 201
    assert body["data"]["kind"] == "registration_prompt"
    assert body["data"]["message"] == "영수증을 등록해 보세요."
    assert body["data"]["targetType"] == "receiptUpload"
    assert body["data"]["targetId"] is None
    assert body["data"]["readAt"] is None
    assert "notificationId" in body["data"]
    assert "createdAt" in body["data"]
    assert "userId" not in body["data"]
    assert "created_at" not in body["data"]
    assert "read_at" not in body["data"]


async def test_create_notification_persists_to_current_user_list(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "kind": "benefit",
        "message": "이번 달 혜택을 확인해 보세요.",
        "targetType": "none",
        "targetId": None,
    }

    async with notification_api_client(postgres_session_factory) as client:
        create_response = await client.post("/api/v1/notifications", json=payload)
        assert create_response.status_code == 201
        created = create_response.json()["data"]
        list_response = await client.get("/api/v1/notifications?limit=2")

    list_body = list_response.json()
    notifications = list_body["data"]["notifications"]
    created_ids = {
        notification["notificationId"]
        for notification in notifications
        if notification["notificationId"] == created["notificationId"]
    }

    assert list_response.status_code == 200
    assert created_ids == {created["notificationId"]}
    assert list_body["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 2,
        "totalCount": 1,
    }


async def test_create_notification_rejects_extra_field_contract(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "kind": "registration_prompt",
        "message": "영수증을 등록해 보세요.",
        "targetType": "receiptUpload",
        "targetId": None,
        "userId": str(TEST_USER_ID),
        "createdAt": "2026-06-28T00:00:00Z",
        "readAt": None,
    }

    async with notification_api_client(postgres_session_factory) as client:
        response = await client.post("/api/v1/notifications", json=payload)

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["path"] == "/api/v1/notifications"


async def test_create_notification_rejects_target_id_mismatch(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    receipt_id = UUID("00000000-0000-0000-0000-000000000701")
    invalid_payloads = [
        {
            "kind": "benefit",
            "message": "영수증 상세를 확인해 보세요.",
            "targetType": "receipt",
            "targetId": None,
        },
        {
            "kind": "benefit",
            "message": "이번 달 혜택을 확인해 보세요.",
            "targetType": "none",
            "targetId": str(receipt_id),
        },
        {
            "kind": "registration_prompt",
            "message": "영수증을 등록해 보세요.",
            "targetType": "receiptUpload",
            "targetId": str(receipt_id),
        },
    ]

    async with notification_api_client(postgres_session_factory) as client:
        responses = [
            await client.post("/api/v1/notifications", json=payload) for payload in invalid_payloads
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert [response.json()["success"] for response in responses] == [False, False, False]


async def test_create_notification_sends_push_to_registered_device(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 로그인한 사용자가 디바이스 FCM 토큰을 등록해 두었다.
    push_sender = FakePushSender()
    async with notification_api_client(
        postgres_session_factory,
        dependency_overrides={get_push_sender: lambda: push_sender},
    ) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "fcm-token-1", "platform": "android"},
        )

        # When: 알림을 생성한다.
        response = await client.post(
            "/api/v1/notifications",
            json={
                "kind": "benefit",
                "message": "이번 달 혜택을 확인해 보세요.",
                "targetType": "none",
                "targetId": None,
            },
        )

    # Then: 등록된 토큰으로 제목/본문이 채워진 푸시가 한 번 발송된다.
    assert response.status_code == 201
    assert len(push_sender.calls) == 1
    sent_tokens, sent_message = push_sender.calls[0]
    assert [token.fcm_token.value for token in sent_tokens] == ["fcm-token-1"]
    assert sent_message.title == "혜택 안내"
    assert sent_message.body == "이번 달 혜택을 확인해 보세요."
    assert sent_message.data["kind"] == "benefit"


async def test_create_notification_removes_token_rejected_by_fcm(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 등록된 토큰이 FCM에서 무효 판정을 받는 상황이다.
    push_sender = FakePushSender(report=PushSendReport(invalid_tokens=("fcm-token-dead",)))
    async with notification_api_client(
        postgres_session_factory,
        dependency_overrides={get_push_sender: lambda: push_sender},
    ) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "fcm-token-dead", "platform": "ios"},
        )

        # When: 알림을 생성한다.
        response = await client.post(
            "/api/v1/notifications",
            json={
                "kind": "benefit",
                "message": "이번 달 혜택을 확인해 보세요.",
                "targetType": "none",
                "targetId": None,
            },
        )

    # Then: 알림 생성은 성공하고 무효 토큰 행은 DB에서 제거된다.
    assert response.status_code == 201
    async with postgres_session_factory() as session:
        rows = list(await session.scalars(select(orm.UserPushToken)))
    assert rows == []

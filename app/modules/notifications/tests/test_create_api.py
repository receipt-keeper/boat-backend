from uuid import UUID, uuid4

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
        "messageType": "transactional",
        "kind": "registration_prompt",
        "title": "영수증 등록 안내",
        "message": "영수증을 등록해 보세요.",
        "resourceType": None,
        "resourceId": None,
    }

    async with notification_api_client(postgres_session_factory) as client:
        response = await client.post("/api/v1/notifications", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["success"] is True
    assert body["status"] == 201
    assert body["data"]["messageType"] == "transactional"
    assert body["data"]["kind"] == "registration_prompt"
    assert body["data"]["title"] == "영수증 등록 안내"
    assert body["data"]["message"] == "영수증을 등록해 보세요."
    assert body["data"]["resourceType"] is None
    assert body["data"]["resourceId"] is None
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
        "messageType": "marketing",
        "kind": "benefit",
        "title": "혜택 안내",
        "message": "이번 달 혜택을 확인해 보세요.",
        "resourceType": None,
        "resourceId": None,
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
        "messageType": "transactional",
        "kind": "registration_prompt",
        "title": "영수증 등록 안내",
        "message": "영수증을 등록해 보세요.",
        "resourceType": "receiptUpload",
        "resourceId": None,
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


async def test_create_notification_rejects_resource_pair_mismatch(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    receipt_id = UUID("00000000-0000-0000-0000-000000000701")
    invalid_payloads = [
        {
            "messageType": "transactional",
            "kind": "benefit",
            "title": "혜택 안내",
            "message": "영수증 상세를 확인해 보세요.",
            "resourceType": "receipt",
            "resourceId": None,
        },
        {
            "messageType": "transactional",
            "kind": "benefit",
            "title": "혜택 안내",
            "message": "이번 달 혜택을 확인해 보세요.",
            "resourceType": None,
            "resourceId": str(receipt_id),
        },
    ]

    async with notification_api_client(postgres_session_factory) as client:
        responses = [
            await client.post("/api/v1/notifications", json=payload) for payload in invalid_payloads
        ]

    assert [response.status_code for response in responses] == [422, 422]
    assert [response.json()["success"] for response in responses] == [False, False]


async def test_create_notification_rejects_oversized_kind_and_title(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    invalid_payloads = [
        {
            "messageType": "transactional",
            "kind": "a" * 51,
            "title": "제목",
            "message": "문구",
        },
        {
            "messageType": "transactional",
            "kind": "benefit",
            "title": "a" * 101,
            "message": "문구",
        },
    ]

    async with notification_api_client(postgres_session_factory) as client:
        responses = [
            await client.post("/api/v1/notifications", json=payload) for payload in invalid_payloads
        ]

    assert [response.status_code for response in responses] == [422, 422]


async def test_create_notification_sends_push_to_registered_device(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 로그인한 사용자가 디바이스를 token으로 등록해 두었다.
    push_sender = FakePushSender()
    async with notification_api_client(
        postgres_session_factory,
        dependency_overrides={get_push_sender: lambda: push_sender},
    ) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"token": "token-1", "platform": "android"},
        )

        # When: 알림을 생성한다.
        response = await client.post(
            "/api/v1/notifications",
            json={
                "messageType": "transactional",
                "kind": "credit_prompt",
                "title": "크레딧 안내",
                "message": "분석 가능 횟수를 확인해 보세요.",
            },
        )

    # Then: 등록된 token으로 제목/본문이 채워진 푸시가 한 번 발송된다.
    assert response.status_code == 201
    assert len(push_sender.calls) == 1
    sent_tokens, sent_message = push_sender.calls[0]
    assert [token.token.value for token in sent_tokens] == ["token-1"]
    assert sent_message.title == "크레딧 안내"
    assert sent_message.body == "분석 가능 횟수를 확인해 보세요."
    assert sent_message.data["kind"] == "credit_prompt"


async def test_create_marketing_notification_skips_push_without_marketing_consent(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 로그인한 사용자가 디바이스를 등록해 두었지만 마케팅 수신에는 동의하지 않았다.
    push_sender = FakePushSender()
    async with notification_api_client(
        postgres_session_factory,
        dependency_overrides={get_push_sender: lambda: push_sender},
    ) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"token": "token-1", "platform": "android"},
        )

        # When: marketing 알림을 생성한다.
        response = await client.post(
            "/api/v1/notifications",
            json={
                "messageType": "marketing",
                "kind": "benefit",
                "title": "혜택 안내",
                "message": "이번 달 혜택을 확인해 보세요.",
            },
        )

    # Then: 알림 생성은 성공하지만 마케팅 동의가 없어 푸시는 발송되지 않는다.
    assert response.status_code == 201
    assert push_sender.calls == []


async def test_create_notification_removes_registration_rejected_by_fcm(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 등록된 token이 FCM에서 무효 판정을 받는 상황이다.
    push_sender = FakePushSender(report=PushSendReport(invalid_tokens=("token-dead",)))
    async with notification_api_client(
        postgres_session_factory,
        dependency_overrides={get_push_sender: lambda: push_sender},
    ) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"token": "token-dead", "platform": "ios"},
        )

        # When: 알림을 생성한다.
        response = await client.post(
            "/api/v1/notifications",
            json={
                "messageType": "transactional",
                "kind": "credit_prompt",
                "title": "크레딧 안내",
                "message": "분석 가능 횟수를 확인해 보세요.",
            },
        )

    # Then: 알림 생성은 성공하고 무효 등록 행은 DB에서 제거된다.
    assert response.status_code == 201
    async with postgres_session_factory() as session:
        rows = list(await session.scalars(select(orm.UserPushToken)))
    assert rows == []


async def test_create_notification_with_resource_pair_returns_created(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    receipt_id = uuid4()
    payload = {
        "messageType": "transactional",
        "kind": "warranty_risk",
        "title": "보증 만료 임박",
        "message": "보증 만료가 임박했습니다.",
        "resourceType": "receipt",
        "resourceId": str(receipt_id),
    }

    async with notification_api_client(postgres_session_factory) as client:
        response = await client.post("/api/v1/notifications", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["data"]["resourceType"] == "receipt"
    assert body["data"]["resourceId"] == str(receipt_id)


async def test_create_notification_with_metadata_returns_created_and_exposed(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "messageType": "transactional",
        "kind": "warranty_risk",
        "title": "보증 만료 임박",
        "message": "보증 만료가 임박했습니다.",
        "metadata": {
            "subCategory": "warranty",
            "productName": "냉장고",
            "expiresAt": "2026-07-12",
        },
    }

    async with notification_api_client(postgres_session_factory) as client:
        response = await client.post("/api/v1/notifications", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["data"]["metadata"] == {
        "subCategory": "warranty",
        "productName": "냉장고",
        "expiresAt": "2026-07-12",
    }


async def test_create_notification_without_metadata_defaults_to_empty_object(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "messageType": "transactional",
        "kind": "registration_prompt",
        "title": "영수증 등록 안내",
        "message": "영수증을 등록해 보세요.",
    }

    async with notification_api_client(postgres_session_factory) as client:
        response = await client.post("/api/v1/notifications", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["data"]["metadata"] == {}


async def test_create_notification_rejects_oversized_metadata(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    too_many_keys_payload = {
        "messageType": "transactional",
        "kind": "registration_prompt",
        "title": "영수증 등록 안내",
        "message": "영수증을 등록해 보세요.",
        "metadata": {f"key{i}": "value" for i in range(51)},
    }
    oversized_key_payload = {
        "messageType": "transactional",
        "kind": "registration_prompt",
        "title": "영수증 등록 안내",
        "message": "영수증을 등록해 보세요.",
        "metadata": {"a" * 41: "value"},
    }
    oversized_value_payload = {
        "messageType": "transactional",
        "kind": "registration_prompt",
        "title": "영수증 등록 안내",
        "message": "영수증을 등록해 보세요.",
        "metadata": {"key": "a" * 501},
    }
    blank_key_payload = {
        "messageType": "transactional",
        "kind": "registration_prompt",
        "title": "영수증 등록 안내",
        "message": "영수증을 등록해 보세요.",
        "metadata": {" key ": "value"},
    }

    async with notification_api_client(postgres_session_factory) as client:
        responses = [
            await client.post("/api/v1/notifications", json=payload)
            for payload in (
                too_many_keys_payload,
                oversized_key_payload,
                oversized_value_payload,
                blank_key_payload,
            )
        ]

    assert [response.status_code for response in responses] == [422, 422, 422, 422]
    assert all(response.json()["success"] is False for response in responses)


async def test_create_notification_accepts_boundary_metadata(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    boundary_metadata = {f"k{i}": "v" * 500 for i in range(49)}
    boundary_metadata["a" * 40] = "boundary"
    payload = {
        "messageType": "transactional",
        "kind": "registration_prompt",
        "title": "영수증 등록 안내",
        "message": "영수증을 등록해 보세요.",
        "metadata": boundary_metadata,
    }

    async with notification_api_client(postgres_session_factory) as client:
        response = await client.post("/api/v1/notifications", json=payload)

    body = response.json()
    assert response.status_code == 201
    assert body["data"]["metadata"] == boundary_metadata

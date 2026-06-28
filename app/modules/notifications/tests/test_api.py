from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications.infrastructure.persistence import orm
from app.modules.notifications.tests.conftest import (
    TEST_USER_ID,
    notification_api_client,
)


async def test_list_notifications_returns_persisted_current_user_notifications(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    newer_notification_id = UUID("00000000-0000-0000-0000-000000000601")
    older_notification_id = UUID("00000000-0000-0000-0000-000000000603")
    other_notification_id = UUID("00000000-0000-0000-0000-000000000602")
    async with postgres_session_factory() as session:
        session.add_all(
            [
                orm.UserNotification(
                    id=newer_notification_id,
                    user_id=TEST_USER_ID,
                    kind="registration_prompt",
                    message="영수증을 등록해 보세요.",
                    target_type="receiptUpload",
                    target_id=None,
                    created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=older_notification_id,
                    user_id=TEST_USER_ID,
                    kind="registration_prompt",
                    message="이전 알림입니다.",
                    target_type="none",
                    target_id=None,
                    created_at=datetime(2026, 6, 28, 9, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=other_notification_id,
                    user_id=UUID("00000000-0000-0000-0000-000000000201"),
                    kind="benefit",
                    message="다른 사용자 알림입니다.",
                    target_type="none",
                    target_id=None,
                    created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                    read_at=None,
                ),
            ]
        )
        await session.commit()

    async with notification_api_client(postgres_session_factory) as client:
        first_response = await client.get("/api/v1/notifications?limit=1")

    first_body = first_response.json()
    assert first_response.status_code == 200
    assert first_body["success"] is True
    assert first_body["status"] == 200
    assert first_body["data"]["notifications"] == [
        {
            "notificationId": str(newer_notification_id),
            "kind": "registration_prompt",
            "message": "영수증을 등록해 보세요.",
            "targetType": "receiptUpload",
            "targetId": None,
            "createdAt": "2026-06-28T10:00:00Z",
            "readAt": None,
        }
    ]
    assert first_body["data"]["pagination"] == {
        "nextCursor": f"2026-06-28T10:00:00Z|{newer_notification_id}",
        "hasNext": True,
        "limit": 1,
        "totalCount": 2,
    }

    inserted_notification_id = UUID("00000000-0000-0000-0000-000000000604")
    async with postgres_session_factory() as session:
        session.add(
            orm.UserNotification(
                id=inserted_notification_id,
                user_id=TEST_USER_ID,
                kind="benefit",
                message="새로 도착한 알림입니다.",
                target_type="none",
                target_id=None,
                created_at=datetime(2026, 6, 28, 11, 0, tzinfo=UTC),
                read_at=None,
            )
        )
        await session.commit()

    async with notification_api_client(postgres_session_factory) as client:
        second_response = await client.get(
            "/api/v1/notifications",
            params={"limit": 1, "cursor": first_body["data"]["pagination"]["nextCursor"]},
        )

    second_body = second_response.json()
    assert second_response.status_code == 200
    assert second_body["data"]["notifications"][0]["notificationId"] == str(older_notification_id)
    assert second_body["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 1,
        "totalCount": 3,
    }


async def test_list_notifications_uses_id_tiebreaker_for_same_created_at_cursor(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    higher_notification_id = UUID("00000000-0000-0000-0000-000000000612")
    lower_notification_id = UUID("00000000-0000-0000-0000-000000000611")
    older_notification_id = UUID("00000000-0000-0000-0000-000000000610")
    async with postgres_session_factory() as session:
        session.add_all(
            [
                orm.UserNotification(
                    id=higher_notification_id,
                    user_id=TEST_USER_ID,
                    kind="registration_prompt",
                    message="같은 시각의 최신 알림입니다.",
                    target_type="none",
                    target_id=None,
                    created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=lower_notification_id,
                    user_id=TEST_USER_ID,
                    kind="registration_prompt",
                    message="같은 시각의 다음 알림입니다.",
                    target_type="none",
                    target_id=None,
                    created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=older_notification_id,
                    user_id=TEST_USER_ID,
                    kind="benefit",
                    message="이전 시각의 알림입니다.",
                    target_type="none",
                    target_id=None,
                    created_at=datetime(2026, 6, 28, 9, 0, tzinfo=UTC),
                    read_at=None,
                ),
            ]
        )
        await session.commit()

    async with notification_api_client(postgres_session_factory) as client:
        first_response = await client.get("/api/v1/notifications?limit=1")

    first_body = first_response.json()
    assert first_response.status_code == 200
    assert first_body["data"]["notifications"][0]["notificationId"] == str(higher_notification_id)

    async with notification_api_client(postgres_session_factory) as client:
        second_response = await client.get(
            "/api/v1/notifications",
            params={"limit": 1, "cursor": first_body["data"]["pagination"]["nextCursor"]},
        )

    second_body = second_response.json()
    assert second_response.status_code == 200
    assert second_body["data"]["notifications"][0]["notificationId"] == str(lower_notification_id)
    assert second_body["data"]["pagination"] == {
        "nextCursor": f"2026-06-28T10:00:00Z|{lower_notification_id}",
        "hasNext": True,
        "limit": 1,
        "totalCount": 3,
    }


async def test_list_notifications_rejects_invalid_cursor(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.get("/api/v1/notifications?cursor=not-a-cursor")

    body = response.json()
    assert response.status_code == 400
    assert body["success"] is False
    assert body["status"] == 400
    assert body["data"]["message"] == "알림 목록 cursor가 올바르지 않습니다."


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
    receipt_id = "00000000-0000-0000-0000-000000000701"
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
            "targetId": receipt_id,
        },
        {
            "kind": "registration_prompt",
            "message": "영수증을 등록해 보세요.",
            "targetType": "receiptUpload",
            "targetId": receipt_id,
        },
    ]

    async with notification_api_client(postgres_session_factory) as client:
        responses = [
            await client.post("/api/v1/notifications", json=payload) for payload in invalid_payloads
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert [response.json()["success"] for response in responses] == [False, False, False]

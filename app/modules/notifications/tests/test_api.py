from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications.infrastructure.persistence import orm
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
)
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


async def test_get_notification_settings_returns_defaults(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.get("/api/v1/notifications/settings")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "pushEnabled": True,
        "marketingConsent": False,
    }


async def test_patch_notification_settings_persists_partial_update(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with notification_api_client(postgres_session_factory) as client:
        default_response = await client.get("/api/v1/notifications/settings")
        patch_response = await client.patch(
            "/api/v1/notifications/settings",
            json={"pushEnabled": False},
        )
        persisted_response = await client.get("/api/v1/notifications/settings")

    assert default_response.status_code == 200
    assert default_response.json()["data"] == {
        "pushEnabled": True,
        "marketingConsent": False,
    }
    assert patch_response.status_code == 200
    assert patch_response.json()["data"] == {
        "pushEnabled": False,
        "marketingConsent": False,
    }
    assert persisted_response.status_code == 200
    assert persisted_response.json()["data"] == {
        "pushEnabled": False,
        "marketingConsent": False,
    }


async def test_update_notification_settings_preserves_concurrent_partial_update(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        session.add(
            orm.NotificationSettings(
                user_id=TEST_USER_ID,
                push_enabled=True,
                marketing_consent=False,
            )
        )
        await session.commit()

    async with (
        postgres_session_factory() as stale_session,
        postgres_session_factory() as concurrent_session,
    ):
        stale_repository = SqlAlchemyNotificationRepository(stale_session)
        concurrent_repository = SqlAlchemyNotificationRepository(concurrent_session)

        stale_settings = await stale_repository.get_settings(user_id=TEST_USER_ID)
        assert stale_settings.push_enabled is True
        assert stale_settings.marketing_consent is False

        await concurrent_repository.update_settings(
            user_id=TEST_USER_ID,
            push_enabled=False,
            marketing_consent=None,
        )
        await concurrent_session.commit()

        updated_settings = await stale_repository.update_settings(
            user_id=TEST_USER_ID,
            push_enabled=None,
            marketing_consent=True,
        )
        await stale_session.commit()

    assert updated_settings.push_enabled is False
    assert updated_settings.marketing_consent is True

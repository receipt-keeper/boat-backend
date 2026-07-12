from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications.infrastructure.persistence import orm
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
)
from app.modules.notifications.tests.conftest import (
    MISSING_NOTIFICATION_ID,
    OTHER_USER_ID,
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
                    message_type="transactional",
                    kind="registration_prompt",
                    title="영수증 등록 안내",
                    message="영수증을 등록해 보세요.",
                    resource_type=None,
                    resource_id=None,
                    created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=older_notification_id,
                    user_id=TEST_USER_ID,
                    message_type="transactional",
                    kind="registration_prompt",
                    title="영수증 등록 안내",
                    message="이전 알림입니다.",
                    resource_type=None,
                    resource_id=None,
                    created_at=datetime(2026, 6, 28, 9, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=other_notification_id,
                    user_id=UUID("00000000-0000-0000-0000-000000000201"),
                    message_type="marketing",
                    kind="benefit",
                    title="혜택 안내",
                    message="다른 사용자 알림입니다.",
                    resource_type=None,
                    resource_id=None,
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
            "messageType": "transactional",
            "kind": "registration_prompt",
            "title": "영수증 등록 안내",
            "message": "영수증을 등록해 보세요.",
            "resourceType": None,
            "resourceId": None,
            "metadata": {},
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
                message_type="marketing",
                kind="benefit",
                title="혜택 안내",
                message="새로 도착한 알림입니다.",
                resource_type=None,
                resource_id=None,
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
        "totalCount": 2,
    }


async def test_list_hides_marketing_when_consent_is_withdrawn_and_restores_it_when_granted(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 거래성 두 건과 마케팅 두 건이 시간순으로 저장되어 있고 마케팅 동의가 있다.
    newest_marketing_id = UUID("00000000-0000-0000-0000-000000000651")
    transactional_id = UUID("00000000-0000-0000-0000-000000000652")
    oldest_marketing_id = UUID("00000000-0000-0000-0000-000000000653")
    oldest_transactional_id = UUID("00000000-0000-0000-0000-000000000654")
    async with postgres_session_factory() as session:
        session.add_all(
            [
                orm.UserNotification(
                    id=newest_marketing_id,
                    user_id=TEST_USER_ID,
                    message_type="marketing",
                    kind="benefit",
                    title="새 혜택",
                    message="최신 마케팅 알림입니다.",
                    resource_type=None,
                    resource_id=None,
                    created_at=datetime(2026, 6, 28, 12, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=transactional_id,
                    user_id=TEST_USER_ID,
                    message_type="transactional",
                    kind="receipt",
                    title="거래성 알림",
                    message="읽음 상태를 보존합니다.",
                    resource_type=None,
                    resource_id=None,
                    created_at=datetime(2026, 6, 28, 11, 0, tzinfo=UTC),
                    read_at=datetime(2026, 6, 28, 11, 30, tzinfo=UTC),
                ),
                orm.UserNotification(
                    id=oldest_marketing_id,
                    user_id=TEST_USER_ID,
                    message_type="marketing",
                    kind="benefit",
                    title="이전 혜택",
                    message="이전 마케팅 알림입니다.",
                    resource_type=None,
                    resource_id=None,
                    created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=oldest_transactional_id,
                    user_id=TEST_USER_ID,
                    message_type="transactional",
                    kind="credit",
                    title="이전 거래성 알림",
                    message="마케팅 동의와 무관합니다.",
                    resource_type=None,
                    resource_id=None,
                    created_at=datetime(2026, 6, 28, 9, 0, tzinfo=UTC),
                    read_at=None,
                ),
            ]
        )
        await session.commit()

    async with notification_api_client(postgres_session_factory) as client:
        # When: 동의를 철회한 뒤 첫 페이지와 cursor 다음 페이지를 조회한다.
        withdraw_response = await client.patch(
            "/api/v1/notifications/settings",
            json={"marketingConsent": False},
        )
        first_response = await client.get("/api/v1/notifications?limit=1")
        second_response = await client.get(
            "/api/v1/notifications",
            params={
                "limit": 1,
                "cursor": first_response.json()["data"]["pagination"]["nextCursor"],
            },
        )
        hidden_mark_response = await client.patch(f"/api/v1/notifications/{newest_marketing_id}")
        empty_page_response = await client.get(
            "/api/v1/notifications",
            params={
                "limit": 1,
                "cursor": f"2026-06-28T09:00:00Z|{oldest_transactional_id}",
            },
        )

        # And: 다시 동의한 뒤 목록을 조회한다.
        grant_response = await client.patch(
            "/api/v1/notifications/settings",
            json={"marketingConsent": True},
        )
        restored_response = await client.get("/api/v1/notifications?limit=10")

    # Then: 철회 중에는 거래성만 total/cursor에 남고, 재동의하면 저장 행이 다시 노출된다.
    assert withdraw_response.status_code == 200
    first_notification = first_response.json()["data"]["notifications"][0]
    assert first_notification["notificationId"] == str(transactional_id)
    assert first_response.json()["data"]["notifications"][0]["readAt"] == "2026-06-28T11:30:00Z"
    assert first_response.json()["data"]["pagination"] == {
        "nextCursor": f"2026-06-28T11:00:00Z|{transactional_id}",
        "hasNext": True,
        "limit": 1,
        "totalCount": 2,
    }
    assert second_response.status_code == 200
    assert second_response.json()["data"]["notifications"][0]["notificationId"] == str(
        oldest_transactional_id
    )
    assert second_response.json()["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 1,
        "totalCount": 2,
    }
    assert hidden_mark_response.status_code == 404
    assert empty_page_response.status_code == 200
    assert empty_page_response.json()["data"] == {
        "notifications": [],
        "pagination": {
            "nextCursor": None,
            "hasNext": False,
            "limit": 1,
            "totalCount": 2,
        },
    }
    assert grant_response.status_code == 200
    restored_notifications = restored_response.json()["data"]["notifications"]
    assert [item["notificationId"] for item in restored_notifications] == [
        str(newest_marketing_id),
        str(transactional_id),
        str(oldest_marketing_id),
        str(oldest_transactional_id),
    ]
    assert restored_response.json()["data"]["pagination"]["totalCount"] == 4
    restored_newest_marketing = restored_notifications[0]
    assert restored_newest_marketing["readAt"] is None


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
                    message_type="transactional",
                    kind="registration_prompt",
                    title="영수증 등록 안내",
                    message="같은 시각의 최신 알림입니다.",
                    resource_type=None,
                    resource_id=None,
                    created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=lower_notification_id,
                    user_id=TEST_USER_ID,
                    message_type="transactional",
                    kind="registration_prompt",
                    title="영수증 등록 안내",
                    message="같은 시각의 다음 알림입니다.",
                    resource_type=None,
                    resource_id=None,
                    created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                    read_at=None,
                ),
                orm.UserNotification(
                    id=older_notification_id,
                    user_id=TEST_USER_ID,
                    message_type="marketing",
                    kind="benefit",
                    title="혜택 안내",
                    message="이전 시각의 알림입니다.",
                    resource_type=None,
                    resource_id=None,
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
        "nextCursor": None,
        "hasNext": False,
        "limit": 1,
        "totalCount": 2,
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


async def test_mark_notification_read_persists_for_current_user(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 현재 사용자의 읽지 않은 알림이 생성되어 있다.
    notification_id = UUID("00000000-0000-0000-0000-000000000701")
    async with postgres_session_factory() as session:
        session.add(
            orm.UserNotification(
                id=notification_id,
                user_id=TEST_USER_ID,
                message_type="transactional",
                kind="registration_prompt",
                title="영수증 등록 안내",
                message="보증 관리를 위해 영수증을 등록해 주세요.",
                resource_type=None,
                resource_id=None,
                metadata_={"subCategory": "receiptUpload"},
                created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                read_at=None,
            )
        )
        await session.commit()

    # When: 읽음 처리 후 목록을 다시 조회한다.
    async with notification_api_client(postgres_session_factory) as client:
        read_response = await client.patch(f"/api/v1/notifications/{notification_id}")
        list_response = await client.get("/api/v1/notifications?limit=10")

    # Then: 읽음 응답과 목록의 같은 알림 모두 readAt과 metadata를 가진다.
    read_body = read_response.json()
    notifications = list_response.json()["data"]["notifications"]
    persisted = next(
        notification
        for notification in notifications
        if notification["notificationId"] == str(notification_id)
    )

    assert read_response.status_code == 200
    assert read_body["data"]["notificationId"] == str(notification_id)
    assert read_body["data"]["readAt"] is not None
    assert read_body["data"]["metadata"] == {"subCategory": "receiptUpload"}
    assert persisted["readAt"] == read_body["data"]["readAt"]
    assert persisted["metadata"] == {"subCategory": "receiptUpload"}


async def test_mark_missing_notification_returns_not_found_envelope(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 현재 사용자에게 존재하지 않는 알림 ID가 있다.
    # When: 읽음 처리를 요청한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.patch(f"/api/v1/notifications/{MISSING_NOTIFICATION_ID}")

    # Then: 404 실패 envelope를 반환한다.
    body = response.json()
    assert response.status_code == 404
    assert body["success"] is False
    assert body["status"] == 404
    assert body["data"]["path"] == f"/api/v1/notifications/{MISSING_NOTIFICATION_ID}"


async def test_mark_foreign_notification_returns_not_found_envelope(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 다른 사용자에게 알림이 생성되어 있다.
    notification_id = UUID("00000000-0000-0000-0000-000000000702")
    async with postgres_session_factory() as session:
        session.add(
            orm.UserNotification(
                id=notification_id,
                user_id=OTHER_USER_ID,
                message_type="marketing",
                kind="benefit",
                title="혜택 안내",
                message="다른 사용자에게만 보이는 알림입니다.",
                resource_type=None,
                resource_id=None,
                created_at=datetime(2026, 6, 28, 10, 0, tzinfo=UTC),
                read_at=None,
            )
        )
        await session.commit()

    # When: 현재 사용자가 그 알림을 읽음 처리하려고 한다.
    async with notification_api_client(
        postgres_session_factory,
        TEST_USER_ID,
    ) as client:
        response = await client.patch(f"/api/v1/notifications/{notification_id}")

    # Then: 존재 여부를 숨기기 위해 404 실패 envelope를 반환한다.
    body = response.json()
    assert response.status_code == 404
    assert body["success"] is False
    assert body["status"] == 404

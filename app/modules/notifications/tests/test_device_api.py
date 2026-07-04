from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications.infrastructure.persistence import orm
from app.modules.notifications.tests.conftest import (
    OTHER_USER_ID,
    TEST_USER_ID,
    notification_api_client,
)


async def _select_all_tokens(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[orm.UserPushToken]:
    async with session_factory() as session:
        result = await session.scalars(select(orm.UserPushToken))
        return list(result)


async def test_register_device_returns_no_content_and_persists_row(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 로그인한 사용자가 디바이스 FCM 토큰을 등록한다.
    payload = {
        "deviceId": "device-1",
        "fcmToken": "fcm-token-1",
        "platform": "android",
    }
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.put("/api/v1/notifications/devices", json=payload)

    # Then: 204를 반환하고 DB에 정확히 1개 행이 저장된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert response.content == b""
    assert len(rows) == 1
    saved_row = rows[0]
    assert (saved_row.user_id, saved_row.device_id, saved_row.fcm_token, saved_row.platform) == (
        TEST_USER_ID,
        "device-1",
        "fcm-token-1",
        "android",
    )


async def test_register_same_device_replaces_token_without_creating_new_row(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 이미 등록된 디바이스가 있다.
    async with notification_api_client(postgres_session_factory) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "fcm-token-1", "platform": "android"},
        )

        # When: 같은 (user, device)로 새 토큰을 재등록한다.
        response = await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "fcm-token-2", "platform": "ios"},
        )

    # Then: 행은 여전히 1개이고 토큰/플랫폼이 교체된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert len(rows) == 1
    saved_row = rows[0]
    assert (saved_row.user_id, saved_row.device_id, saved_row.fcm_token, saved_row.platform) == (
        TEST_USER_ID,
        "device-1",
        "fcm-token-2",
        "ios",
    )


async def test_register_same_fcm_token_for_other_user_moves_ownership(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: TEST_USER_ID의 device-1에 fcm-token-shared가 등록되어 있다.
    async with notification_api_client(postgres_session_factory, TEST_USER_ID) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={
                "deviceId": "device-1",
                "fcmToken": "fcm-token-shared",
                "platform": "android",
            },
        )

    # When: 다른 사용자가 같은 fcm_token을 자신의 다른 device_id로 등록한다.
    async with notification_api_client(postgres_session_factory, OTHER_USER_ID) as client:
        response = await client.put(
            "/api/v1/notifications/devices",
            json={
                "deviceId": "device-2",
                "fcmToken": "fcm-token-shared",
                "platform": "ios",
            },
        )

    # Then: 기존 소유 행은 삭제되고 새 소유 행 1개만 남는다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert len(rows) == 1
    saved_row = rows[0]
    assert (saved_row.user_id, saved_row.device_id, saved_row.fcm_token, saved_row.platform) == (
        OTHER_USER_ID,
        "device-2",
        "fcm-token-shared",
        "ios",
    )


async def test_register_device_rejects_empty_device_id(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 빈 deviceId로 등록을 시도한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "", "fcmToken": "fcm-token-1", "platform": "android"},
        )

    # Then: 422로 거부되고 DB에는 아무 행도 남지 않는다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 422
    assert rows == []


async def test_register_device_rejects_empty_and_oversized_fcm_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 빈 fcmToken과 513자 fcmToken으로 각각 등록을 시도한다.
    async with notification_api_client(postgres_session_factory) as client:
        empty_response = await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "", "platform": "android"},
        )
        oversized_response = await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "a" * 513, "platform": "android"},
        )

    # Then: 둘 다 422로 거부되고 DB에는 아무 행도 남지 않는다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert empty_response.status_code == 422
    assert oversized_response.status_code == 422
    assert rows == []


async def test_register_device_rejects_unsupported_platform(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 지원하지 않는 platform 값으로 등록을 시도한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "fcm-token-1", "platform": "web"},
        )

    # Then: 스키마 레벨에서 422로 거부되고 DB에는 아무 행도 남지 않는다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 422
    assert rows == []


async def test_unregister_device_deletes_row_and_returns_no_content(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 등록된 디바이스가 있다.
    async with notification_api_client(postgres_session_factory) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "fcm-token-1", "platform": "android"},
        )

        # When: 그 디바이스를 해제한다.
        response = await client.delete("/api/v1/notifications/devices/device-1")

    # Then: 204를 반환하고 DB 행이 삭제된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert response.content == b""
    assert rows == []


async def test_unregister_missing_device_is_idempotent_no_content(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 등록된 적 없는 device_id를 해제한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.delete("/api/v1/notifications/devices/never-registered")

    # Then: 멱등하게 204를 반환한다.
    assert response.status_code == 204
    assert response.content == b""


async def test_unregister_foreign_device_keeps_row_and_returns_no_content(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 다른 사용자가 등록한 디바이스가 있다.
    async with notification_api_client(postgres_session_factory, OTHER_USER_ID) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"deviceId": "device-1", "fcmToken": "fcm-token-1", "platform": "android"},
        )

    # When: 현재 사용자가 그 device_id 해제를 시도한다.
    async with notification_api_client(postgres_session_factory, TEST_USER_ID) as client:
        response = await client.delete("/api/v1/notifications/devices/device-1")

    # Then: 존재 여부를 숨기며 204를 반환하고, 다른 사용자의 행은 그대로 유지된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert len(rows) == 1
    assert rows[0].user_id == OTHER_USER_ID
    assert rows[0].device_id == "device-1"

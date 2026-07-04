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
    # Given/When: 로그인한 사용자가 디바이스 FID를 등록한다.
    payload = {"fid": "fid-1", "platform": "android"}
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.put("/api/v1/notifications/devices", json=payload)

    # Then: 204를 반환하고 DB에 정확히 1개 행이 저장된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert response.content == b""
    assert len(rows) == 1
    saved_row = rows[0]
    assert (saved_row.user_id, saved_row.fid, saved_row.platform) == (
        TEST_USER_ID,
        "fid-1",
        "android",
    )


async def test_register_same_fid_updates_row_without_creating_new_row(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 이미 등록된 디바이스가 있다.
    async with notification_api_client(postgres_session_factory) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "fid-1", "platform": "android"},
        )

        # When: 같은 FID로 다른 플랫폼을 재등록한다.
        response = await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "fid-1", "platform": "ios"},
        )

    # Then: 행이 늘지 않고 기존 행이 갱신된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert len(rows) == 1
    assert (rows[0].user_id, rows[0].fid, rows[0].platform) == (TEST_USER_ID, "fid-1", "ios")


async def test_register_same_fid_by_other_user_transfers_ownership(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 현재 사용자가 등록해 둔 FID가 있다.
    async with notification_api_client(postgres_session_factory, TEST_USER_ID) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "fid-shared", "platform": "android"},
        )

    # When: 같은 기기에서 다른 사용자가 같은 FID를 등록한다.
    async with notification_api_client(postgres_session_factory, OTHER_USER_ID) as client:
        response = await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "fid-shared", "platform": "android"},
        )

    # Then: 행은 1개로 유지되고 소유자가 새 사용자로 이전된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert len(rows) == 1
    assert (rows[0].user_id, rows[0].fid) == (OTHER_USER_ID, "fid-shared")


async def test_register_device_with_blank_fid_returns_422(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 빈 fid로 등록을 시도한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "", "platform": "android"},
        )

    # Then: 422를 반환하고 행이 저장되지 않는다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert rows == []


async def test_register_device_with_oversized_fid_returns_422(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 256자 fid로 등록을 시도한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "a" * 256, "platform": "ios"},
        )

    # Then: DB에 닿기 전에 422로 거부된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert rows == []


async def test_register_device_with_unsupported_platform_returns_422(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 지원하지 않는 platform으로 등록을 시도한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "fid-1", "platform": "web"},
        )

    # Then: 스키마 검증에서 422로 거부된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert rows == []


async def test_unregister_device_deletes_row_and_returns_no_content(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 등록된 디바이스가 있다.
    async with notification_api_client(postgres_session_factory) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "fid-1", "platform": "android"},
        )

        # When: 등록을 해제한다.
        response = await client.delete("/api/v1/notifications/devices/fid-1")

    # Then: 204를 반환하고 행이 삭제된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert response.content == b""
    assert rows == []


async def test_unregister_missing_device_is_idempotent(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given/When: 등록된 적 없는 fid를 해제한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.delete("/api/v1/notifications/devices/missing-fid")

    # Then: 멱등하게 204를 반환한다.
    assert response.status_code == 204
    assert response.content == b""


async def test_unregister_other_users_device_keeps_row(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 다른 사용자가 등록한 디바이스가 있다.
    async with notification_api_client(postgres_session_factory, TEST_USER_ID) as client:
        await client.put(
            "/api/v1/notifications/devices",
            json={"fid": "fid-1", "platform": "android"},
        )

    # When: 다른 사용자가 그 fid의 해제를 시도한다.
    async with notification_api_client(postgres_session_factory, OTHER_USER_ID) as client:
        response = await client.delete("/api/v1/notifications/devices/fid-1")

    # Then: 204를 반환하지만 소유자가 다른 행은 유지된다.
    rows = await _select_all_tokens(postgres_session_factory)
    assert response.status_code == 204
    assert len(rows) == 1
    assert rows[0].user_id == TEST_USER_ID

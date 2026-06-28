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
    notification_id = UUID("00000000-0000-0000-0000-000000000601")
    other_notification_id = UUID("00000000-0000-0000-0000-000000000602")
    async with postgres_session_factory() as session:
        session.add_all(
            [
                orm.UserNotification(
                    id=notification_id,
                    user_id=TEST_USER_ID,
                    kind="registration_prompt",
                    message="영수증을 등록해 보세요.",
                    target_type="receiptUpload",
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
        response = await client.get("/api/v1/notifications?limit=2")

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["status"] == 200
    assert body["data"]["notifications"] == [
        {
            "notificationId": str(notification_id),
            "kind": "registration_prompt",
            "message": "영수증을 등록해 보세요.",
            "targetType": "receiptUpload",
            "targetId": None,
            "createdAt": "2026-06-28T09:00:00Z",
            "readAt": None,
        }
    ]
    assert body["data"]["pagination"] == {
        "nextCursor": None,
        "hasNext": False,
        "limit": 2,
        "totalCount": 1,
    }

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.notifications.application.commands.delete_notification.command import (
    DeleteNotificationCommand,
)
from app.modules.notifications.application.commands.delete_notification.use_case import (
    DeleteNotificationCommandUseCase,
)
from app.modules.notifications.application.commands.send_notification_push.command import (
    SendNotificationPushCommand,
)
from app.modules.notifications.application.commands.send_notification_push.use_case import (
    SendNotificationPushCommandUseCase,
)
from app.modules.notifications.application.ports.push_sender import (
    PushMessage,
    PushSender,
    PushSendReport,
)
from app.modules.notifications.domain.model import UserPushToken
from app.modules.notifications.domain.value_objects import DevicePlatform, NotificationMessageType
from app.modules.notifications.infrastructure.persistence import orm
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyPushTokenRepository,
)
from app.modules.notifications.tests.conftest import (
    MISSING_NOTIFICATION_ID,
    OTHER_USER_ID,
    TEST_USER_ID,
    notification_api_client,
)


class _BlockingPushSender(PushSender):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def send(
        self,
        *,
        tokens: Sequence[UserPushToken],
        message: PushMessage,
    ) -> PushSendReport:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return PushSendReport()


async def test_delete_notification_returns_204_for_owned_marketing_notification(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: marketing 동의와 무관하게 현재 사용자의 marketing 알림이 저장되어 있다.
    notification_id = UUID("00000000-0000-0000-0000-000000000801")
    async with postgres_session_factory() as session:
        session.add(
            orm.UserNotification(
                id=notification_id,
                user_id=TEST_USER_ID,
                message_type="marketing",
                kind="benefit",
                title="혜택 안내",
                message="혜택을 확인해 보세요.",
                resource_type=None,
                resource_id=None,
                created_at=datetime(2026, 7, 17, tzinfo=UTC),
                read_at=None,
            )
        )
        await session.commit()

    # When: 현재 사용자가 알림 삭제 API를 호출한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.delete(f"/api/v1/notifications/{notification_id}")

    # Then: 본문 없는 204 응답을 반환한다.
    assert response.status_code == 204
    assert response.content == b""


async def test_delete_waits_for_in_flight_push_row_lock(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    notification_id = UUID("00000000-0000-0000-0000-000000000803")
    created_at = datetime(2026, 7, 17, tzinfo=UTC)
    async with postgres_session_factory() as session:
        session.add(
            orm.UserNotification(
                id=notification_id,
                user_id=TEST_USER_ID,
                category="warranty",
                message_type=NotificationMessageType.TRANSACTIONAL,
                kind="warranty_risk",
                title="보증 만료 임박",
                message="보증 만료가 임박했습니다.",
                resource_type=None,
                resource_id=None,
                created_at=created_at,
                read_at=None,
            )
        )
        session.add(
            orm.UserPushToken(
                id=UUID("00000000-0000-0000-0000-000000000804"),
                user_id=TEST_USER_ID,
                token="token-delete-race",
                platform=DevicePlatform.ANDROID.value,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.commit()

    push_session = postgres_session_factory()
    delete_session = postgres_session_factory()
    push_sender = _BlockingPushSender()
    push_task = asyncio.create_task(
        SendNotificationPushCommandUseCase(
            notification_repository=SqlAlchemyNotificationRepository(push_session),
            push_token_repository=SqlAlchemyPushTokenRepository(push_session),
            push_sender=push_sender,
            unit_of_work=SqlAlchemyUnitOfWork(push_session),
        ).execute(
            SendNotificationPushCommand(
                user_id=TEST_USER_ID,
                notification_id=notification_id,
                message_type=NotificationMessageType.TRANSACTIONAL,
                kind="warranty_risk",
                title="보증 만료 임박",
                message="보증 만료가 임박했습니다.",
                resource_type=None,
                resource_id=None,
            )
        )
    )
    delete_task: asyncio.Task[None] | None = None

    try:
        await asyncio.wait_for(push_sender.started.wait(), timeout=1)
        delete_task = asyncio.create_task(
            DeleteNotificationCommandUseCase(
                notification_repository=SqlAlchemyNotificationRepository(delete_session),
                unit_of_work=SqlAlchemyUnitOfWork(delete_session),
            ).execute(
                DeleteNotificationCommand(
                    user_id=TEST_USER_ID,
                    notification_id=notification_id,
                )
            )
        )
        await asyncio.sleep(0.05)
        assert not delete_task.done()

        push_sender.release.set()
        await push_task
        await push_session.close()
        await asyncio.wait_for(delete_task, timeout=1)
        assert push_sender.calls == 1
    finally:
        push_sender.release.set()
        await push_session.close()
        if not push_task.done():
            await push_task
        if delete_task is not None:
            await asyncio.gather(delete_task, return_exceptions=True)
        await delete_session.close()

    async with postgres_session_factory() as session:
        assert await session.get(orm.UserNotification, notification_id) is None


async def test_delete_notification_returns_404_for_foreign_notification(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 다른 사용자가 소유한 알림이 저장되어 있다.
    notification_id = UUID("00000000-0000-0000-0000-000000000802")
    async with postgres_session_factory() as session:
        session.add(
            orm.UserNotification(
                id=notification_id,
                user_id=OTHER_USER_ID,
                message_type="transactional",
                kind="benefit",
                title="혜택 안내",
                message="다른 사용자 알림입니다.",
                resource_type=None,
                resource_id=None,
                created_at=datetime(2026, 7, 17, tzinfo=UTC),
                read_at=None,
            )
        )
        await session.commit()

    # When: 현재 사용자가 다른 사용자의 알림 삭제를 시도한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.delete(f"/api/v1/notifications/{notification_id}")

    # Then: 소유권을 숨기는 404 실패 envelope를 반환한다.
    body = response.json()
    assert response.status_code == 404
    assert body["success"] is False
    assert body["status"] == 404
    assert body["data"]["path"] == f"/api/v1/notifications/{notification_id}"


async def test_delete_missing_notification_returns_404(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 현재 사용자에게 존재하지 않는 알림 ID가 있다.

    # When: 존재하지 않는 알림 삭제 API를 호출한다.
    async with notification_api_client(postgres_session_factory) as client:
        response = await client.delete(f"/api/v1/notifications/{MISSING_NOTIFICATION_ID}")

    # Then: 404 실패 envelope를 반환한다.
    body = response.json()
    assert response.status_code == 404
    assert body["data"]["path"] == f"/api/v1/notifications/{MISSING_NOTIFICATION_ID}"

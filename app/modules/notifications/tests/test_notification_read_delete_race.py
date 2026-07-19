from datetime import UTC, datetime
from uuid import UUID

import anyio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import NotFoundError
from app.modules.notifications.application.commands.delete_notification.command import (
    DeleteNotificationCommand,
)
from app.modules.notifications.application.commands.delete_notification.use_case import (
    DeleteNotificationCommandUseCase,
)
from app.modules.notifications.application.commands.mark_notification_read.command import (
    MarkNotificationReadCommand,
)
from app.modules.notifications.application.commands.mark_notification_read.use_case import (
    MarkNotificationReadCommandUseCase,
)
from app.modules.notifications.infrastructure.persistence import orm
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
)
from app.modules.notifications.tests.conftest import TEST_USER_ID


class _BlockingDeleteRepository(SqlAlchemyNotificationRepository):
    def __init__(
        self,
        session: AsyncSession,
        delete_flushed: anyio.Event,
        release_delete: anyio.Event,
    ) -> None:
        super().__init__(session)
        self._delete_flushed = delete_flushed
        self._release_delete = release_delete

    async def delete_by_id_for_user(self, *, notification_id: UUID, user_id: UUID) -> bool:
        deleted = await super().delete_by_id_for_user(
            notification_id=notification_id,
            user_id=user_id,
        )
        self._delete_flushed.set()
        await self._release_delete.wait()
        return deleted


class _LockObservationRepository(SqlAlchemyNotificationRepository):
    def __init__(self, session: AsyncSession, lock_requested: anyio.Event) -> None:
        super().__init__(session)
        self._lock_requested = lock_requested

    async def _find_record_by_id_for_user(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
        for_update: bool = False,
    ) -> orm.UserNotification | None:
        if for_update:
            self._lock_requested.set()
        return await super()._find_record_by_id_for_user(
            notification_id=notification_id,
            user_id=user_id,
            for_update=for_update,
        )


async def test_mark_read_returns_not_found_when_delete_wins_row_lock(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 현재 사용자의 알림이 있고 삭제 트랜잭션이 해당 행을 먼저 잠근다.
    notification_id = UUID("00000000-0000-0000-0000-000000000901")
    async with postgres_session_factory() as session:
        session.add(
            orm.UserNotification(
                id=notification_id,
                user_id=TEST_USER_ID,
                message_type="transactional",
                kind="benefit",
                title="알림",
                message="message",
                resource_type=None,
                resource_id=None,
                created_at=datetime(2026, 7, 17, tzinfo=UTC),
                read_at=None,
            )
        )
        await session.commit()

    delete_flushed = anyio.Event()
    release_delete = anyio.Event()
    lock_requested = anyio.Event()
    delete_finished = anyio.Event()
    mark_read_finished = anyio.Event()
    mark_read_error: NotFoundError | None = None
    delete_session = postgres_session_factory()
    mark_read_session = postgres_session_factory()

    async def run_delete() -> None:
        await DeleteNotificationCommandUseCase(
            notification_repository=_BlockingDeleteRepository(
                delete_session,
                delete_flushed,
                release_delete,
            ),
            unit_of_work=SqlAlchemyUnitOfWork(delete_session),
        ).execute(
            DeleteNotificationCommand(
                user_id=TEST_USER_ID,
                notification_id=notification_id,
            )
        )
        delete_finished.set()

    async def run_mark_read() -> None:
        nonlocal mark_read_error
        try:
            await MarkNotificationReadCommandUseCase(
                notification_repository=_LockObservationRepository(
                    mark_read_session,
                    lock_requested,
                ),
                unit_of_work=SqlAlchemyUnitOfWork(mark_read_session),
            ).execute(
                MarkNotificationReadCommand(
                    user_id=TEST_USER_ID,
                    notification_id=notification_id,
                )
            )
        except NotFoundError as error:
            mark_read_error = error
        finally:
            mark_read_finished.set()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(run_delete)
        with anyio.fail_after(1):
            await delete_flushed.wait()

        task_group.start_soon(run_mark_read)
        with anyio.fail_after(1):
            await lock_requested.wait()

        # Then: 읽음 처리는 삭제 승패를 500이 아닌 알림 없음으로 반환한다.
        release_delete.set()
        with anyio.fail_after(1):
            await delete_finished.wait()
        with anyio.fail_after(1):
            await mark_read_finished.wait()
        assert isinstance(mark_read_error, NotFoundError)

    await delete_session.close()
    await mark_read_session.close()

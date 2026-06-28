from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.ports.notification_repository import (
    NotificationListCursor,
    NotificationListResult,
    NotificationRepository,
)
from app.modules.notifications.domain.model import NotificationSettings, UserNotification
from app.modules.notifications.infrastructure.persistence import mapper, orm


class SqlAlchemyNotificationRepository(NotificationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, notification: UserNotification) -> UserNotification:
        self._session.add(mapper.notification_to_record(notification))
        await self._session.flush()
        return notification

    async def list_by_user(
        self,
        *,
        user_id: UUID,
        cursor: NotificationListCursor | None,
        limit: int,
    ) -> NotificationListResult:
        total_count = await self._session.scalar(
            select(func.count())
            .select_from(orm.UserNotification)
            .where(orm.UserNotification.user_id == user_id)
        )
        query = (
            select(orm.UserNotification)
            .where(orm.UserNotification.user_id == user_id)
            .order_by(
                orm.UserNotification.created_at.desc(),
                orm.UserNotification.id.desc(),
            )
            .limit(limit + 1)
        )
        if cursor is not None:
            query = query.where(
                or_(
                    orm.UserNotification.created_at < cursor.created_at,
                    and_(
                        orm.UserNotification.created_at == cursor.created_at,
                        orm.UserNotification.id < cursor.notification_id,
                    ),
                )
            )
        records = tuple(await self._session.scalars(query))
        return NotificationListResult(
            notifications=tuple(
                mapper.notification_to_domain(record) for record in records[:limit]
            ),
            has_next=len(records) > limit,
            total_count=total_count or 0,
        )

    async def find_by_id_for_user(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
    ) -> UserNotification | None:
        record = await self._find_record_by_id_for_user(
            notification_id=notification_id,
            user_id=user_id,
        )
        if record is None:
            return None
        return mapper.notification_to_domain(record)

    async def mark_read(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
        read_at: datetime,
    ) -> UserNotification | None:
        record = await self._find_record_by_id_for_user(
            notification_id=notification_id,
            user_id=user_id,
        )
        if record is None:
            return None
        record.read_at = read_at
        await self._session.flush()
        return mapper.notification_to_domain(record)

    async def get_settings(self, *, user_id: UUID) -> NotificationSettings:
        record = await self._session.get(orm.NotificationSettings, user_id)
        if record is None:
            return NotificationSettings.create(user_id=user_id)
        return mapper.settings_to_domain(record)

    async def update_settings(
        self,
        *,
        user_id: UUID,
        push_enabled: bool | None,
        marketing_consent: bool | None,
    ) -> NotificationSettings:
        update_values: dict[str, bool] = {}
        if push_enabled is not None:
            update_values["push_enabled"] = push_enabled
        if marketing_consent is not None:
            update_values["marketing_consent"] = marketing_consent

        if update_values:
            insert_statement = postgresql_insert(orm.NotificationSettings).values(
                user_id=user_id,
                **update_values,
            )
            await self._session.execute(
                insert_statement.on_conflict_do_update(
                    index_elements=[orm.NotificationSettings.user_id],
                    set_={
                        **update_values,
                        "updated_at": func.now(),
                    },
                )
            )
        await self._session.flush()

        record = await self._session.scalar(
            select(orm.NotificationSettings)
            .where(orm.NotificationSettings.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        if record is None:
            return NotificationSettings.create(user_id=user_id)
        return mapper.settings_to_domain(record)

    async def _find_record_by_id_for_user(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
    ) -> orm.UserNotification | None:
        return await self._session.scalar(
            select(orm.UserNotification).where(
                orm.UserNotification.id == notification_id,
                orm.UserNotification.user_id == user_id,
            )
        )

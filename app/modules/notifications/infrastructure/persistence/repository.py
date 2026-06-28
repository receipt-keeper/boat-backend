from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.ports.notification_repository import (
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
        offset: int,
        limit: int,
    ) -> NotificationListResult:
        total_count = await self._session.scalar(
            select(func.count())
            .select_from(orm.UserNotification)
            .where(orm.UserNotification.user_id == user_id)
        )
        records = await self._session.scalars(
            select(orm.UserNotification)
            .where(orm.UserNotification.user_id == user_id)
            .order_by(
                orm.UserNotification.created_at.desc(),
                orm.UserNotification.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return NotificationListResult(
            notifications=tuple(mapper.notification_to_domain(record) for record in records),
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
        settings: NotificationSettings,
    ) -> NotificationSettings:
        record = await self._session.get(orm.NotificationSettings, settings.id)
        if record is None:
            self._session.add(mapper.settings_to_record(settings))
            await self._session.flush()
            return settings

        record.push_enabled = settings.push_enabled
        record.marketing_consent = settings.marketing_consent
        await self._session.flush()
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

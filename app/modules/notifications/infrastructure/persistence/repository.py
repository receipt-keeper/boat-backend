from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, delete, exists, func, or_, select, true
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.notifications.application.ports.notification_repository import (
    NotificationListCursor,
    NotificationListResult,
    NotificationRepository,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)
from app.modules.notifications.domain.model import (
    NotificationSettings,
    UserNotification,
    UserPushToken,
)
from app.modules.notifications.domain.value_objects import DevicePlatform
from app.modules.notifications.infrastructure.persistence import mapper
from app.modules.notifications.infrastructure.persistence.orm import (
    NotificationSettings as NotificationSettingsRecord,
)
from app.modules.notifications.infrastructure.persistence.orm import (
    UserNotification as UserNotificationRecord,
)
from app.modules.notifications.infrastructure.persistence.orm import (
    UserPushToken as UserPushTokenRecord,
)
from app.modules.notifications.infrastructure.persistence.schedule_occurrence_repository import (
    SqlAlchemyScheduleOccurrenceRepository,
)
from app.modules.notifications.infrastructure.persistence.schedule_rule_repository import (
    SqlAlchemyNotificationScheduleRuleRepository,
)

__all__ = (
    "SqlAlchemyNotificationRepository",
    "SqlAlchemyNotificationScheduleRuleRepository",
    "SqlAlchemyPushTokenRepository",
    "SqlAlchemyScheduleOccurrenceRepository",
)


class PushTokenUpsertMissingRecordError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("push token upsert 이후 레코드를 찾을 수 없습니다.")


class NotificationSettingsLockMissingRecordError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("notification settings 잠금 이후 레코드를 찾을 수 없습니다.")


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
        marketing_visible = exists(
            select(NotificationSettingsRecord.user_id).where(
                NotificationSettingsRecord.user_id == user_id,
                NotificationSettingsRecord.marketing_consent.is_(True),
            )
        )
        filters = [
            UserNotificationRecord.user_id == user_id,
            or_(UserNotificationRecord.message_type != "marketing", marketing_visible),
        ]
        visible_notifications = (
            select(UserNotificationRecord).where(*filters).cte("visible_notifications")
        )
        notification = aliased(UserNotificationRecord, visible_notifications)
        total = (
            select(func.count().label("total_count")).select_from(visible_notifications).subquery()
        )
        page = (
            select(notification)
            .order_by(
                notification.created_at.desc(),
                notification.id.desc(),
            )
            .limit(limit + 1)
        )
        if cursor is not None:
            page = page.where(
                or_(
                    notification.created_at < cursor.created_at,
                    and_(
                        notification.created_at == cursor.created_at,
                        notification.id < cursor.notification_id,
                    ),
                )
            )
        page_notification = aliased(UserNotificationRecord, page.subquery())
        rows = tuple(
            (
                await self._session.execute(
                    select(page_notification, total.c.total_count)
                    .select_from(total.outerjoin(page_notification, true()))
                    .order_by(
                        page_notification.created_at.desc(),
                        page_notification.id.desc(),
                    )
                )
            ).tuples()
        )
        records = tuple(row[0] for row in rows if row[0] is not None)
        return NotificationListResult(
            notifications=tuple(
                mapper.notification_to_domain(record) for record in records[:limit]
            ),
            has_next=len(records) > limit,
            total_count=rows[0][1],
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

    async def find_by_id_for_user_for_update(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
    ) -> UserNotification | None:
        record = await self._find_record_by_id_for_user(
            notification_id=notification_id,
            user_id=user_id,
            for_update=True,
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
            for_update=True,
        )
        if record is None:
            return None
        record.read_at = read_at
        await self._session.flush()
        return mapper.notification_to_domain(record)

    async def delete_by_id_for_user(self, *, notification_id: UUID, user_id: UUID) -> bool:
        record = await self._session.scalar(
            select(UserNotificationRecord)
            .where(
                UserNotificationRecord.id == notification_id,
                UserNotificationRecord.user_id == user_id,
            )
            .with_for_update()
        )
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.flush()
        return True

    async def get_settings(self, *, user_id: UUID) -> NotificationSettings:
        record = await self._session.get(NotificationSettingsRecord, user_id)
        if record is None:
            return NotificationSettings.create(user_id=user_id)
        return mapper.settings_to_domain(record)

    async def get_settings_for_update(self, *, user_id: UUID) -> NotificationSettings:
        insert_statement = postgresql_insert(NotificationSettingsRecord).values(user_id=user_id)
        await self._session.execute(
            insert_statement.on_conflict_do_nothing(
                index_elements=[NotificationSettingsRecord.user_id]
            )
        )
        await self._session.flush()

        record = await self._session.scalar(
            select(NotificationSettingsRecord)
            .where(NotificationSettingsRecord.user_id == user_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if record is None:
            raise NotificationSettingsLockMissingRecordError()
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
            insert_statement = postgresql_insert(NotificationSettingsRecord).values(
                user_id=user_id,
                **update_values,
            )
            await self._session.execute(
                insert_statement.on_conflict_do_update(
                    index_elements=[NotificationSettingsRecord.user_id],
                    set_={
                        **update_values,
                        "updated_at": func.now(),
                    },
                )
            )
        await self._session.flush()

        record = await self._session.scalar(
            select(NotificationSettingsRecord)
            .where(NotificationSettingsRecord.user_id == user_id)
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
        for_update: bool = False,
    ) -> UserNotificationRecord | None:
        marketing_visible = exists(
            select(NotificationSettingsRecord.user_id).where(
                NotificationSettingsRecord.user_id == user_id,
                NotificationSettingsRecord.marketing_consent.is_(True),
            )
        )
        filters = [
            UserNotificationRecord.id == notification_id,
            UserNotificationRecord.user_id == user_id,
            or_(UserNotificationRecord.message_type != "marketing", marketing_visible),
        ]
        statement = select(UserNotificationRecord).where(*filters)
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)


class SqlAlchemyPushTokenRepository(PushTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(
        self,
        *,
        user_id: UUID,
        token: str,
        platform: DevicePlatform,
    ) -> UserPushToken:
        insert_statement = postgresql_insert(UserPushTokenRecord).values(
            user_id=user_id,
            token=token,
            platform=platform.value,
        )
        await self._session.execute(
            insert_statement.on_conflict_do_update(
                index_elements=[UserPushTokenRecord.token],
                set_={
                    "user_id": user_id,
                    "platform": platform.value,
                    "updated_at": func.now(),
                },
            )
        )
        await self._session.flush()

        record = await self._session.scalar(
            select(UserPushTokenRecord)
            .where(UserPushTokenRecord.token == token)
            .execution_options(populate_existing=True)
        )
        if record is None:
            raise PushTokenUpsertMissingRecordError()
        return mapper.push_token_to_domain(record)

    async def unregister(self, *, user_id: UUID, token: str) -> None:
        await self._session.execute(
            delete(UserPushTokenRecord).where(
                UserPushTokenRecord.user_id == user_id,
                UserPushTokenRecord.token == token,
            )
        )
        await self._session.flush()

    async def list_by_user(self, *, user_id: UUID) -> tuple[UserPushToken, ...]:
        records = await self._session.scalars(
            select(UserPushTokenRecord)
            .where(UserPushTokenRecord.user_id == user_id)
            .order_by(UserPushTokenRecord.created_at, UserPushTokenRecord.id)
        )
        return tuple(mapper.push_token_to_domain(record) for record in records)

    async def delete_by_tokens(self, *, tokens: Sequence[str]) -> None:
        if not tokens:
            return
        await self._session.execute(
            delete(UserPushTokenRecord).where(UserPushTokenRecord.token.in_(list(tokens)))
        )
        await self._session.flush()

    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        await self._session.execute(
            delete(UserPushTokenRecord).where(UserPushTokenRecord.user_id == user_id)
        )
        await self._session.flush()

    async def delete_stale(self, *, older_than: datetime) -> int:
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                delete(UserPushTokenRecord).where(UserPushTokenRecord.updated_at < older_than)
            ),
        )
        await self._session.flush()
        return result.rowcount or 0

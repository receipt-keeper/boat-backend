from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

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
            .select_from(UserNotificationRecord)
            .where(UserNotificationRecord.user_id == user_id)
        )
        query = (
            select(UserNotificationRecord)
            .where(UserNotificationRecord.user_id == user_id)
            .order_by(
                UserNotificationRecord.created_at.desc(),
                UserNotificationRecord.id.desc(),
            )
            .limit(limit + 1)
        )
        if cursor is not None:
            query = query.where(
                or_(
                    UserNotificationRecord.created_at < cursor.created_at,
                    and_(
                        UserNotificationRecord.created_at == cursor.created_at,
                        UserNotificationRecord.id < cursor.notification_id,
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
        record = await self._session.get(NotificationSettingsRecord, user_id)
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
    ) -> UserNotificationRecord | None:
        return await self._session.scalar(
            select(UserNotificationRecord).where(
                UserNotificationRecord.id == notification_id,
                UserNotificationRecord.user_id == user_id,
            )
        )


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

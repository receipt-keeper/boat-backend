from uuid import UUID

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.ports.schedule_occurrence_repository import (
    ScheduleOccurrenceRepository,
)
from app.modules.notifications.domain.schedule_occurrence import ScheduleOccurrenceKey
from app.modules.notifications.infrastructure.persistence.schedule_occurrence_orm import (
    NotificationScheduleOccurrence,
)


class SqlAlchemyScheduleOccurrenceRepository(ScheduleOccurrenceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(self, *, occurrence: ScheduleOccurrenceKey) -> bool:
        insert_statement = (
            postgresql_insert(NotificationScheduleOccurrence)
            .values(
                campaign_key=occurrence.campaign_key,
                target_type=occurrence.target_type.value,
                target_id=occurrence.target_id,
                occurrence_on=occurrence.occurrence_on,
                notification_id=None,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    NotificationScheduleOccurrence.campaign_key,
                    NotificationScheduleOccurrence.target_type,
                    NotificationScheduleOccurrence.target_id,
                    NotificationScheduleOccurrence.occurrence_on,
                ]
            )
            .returning(NotificationScheduleOccurrence.campaign_key)
        )
        result = await self._session.scalar(insert_statement)
        await self._session.flush()
        return result is not None

    async def bind_notification(
        self,
        *,
        occurrence: ScheduleOccurrenceKey,
        notification_id: UUID,
    ) -> None:
        await self._session.execute(
            update(NotificationScheduleOccurrence)
            .where(
                NotificationScheduleOccurrence.campaign_key == occurrence.campaign_key,
                NotificationScheduleOccurrence.target_type == occurrence.target_type.value,
                NotificationScheduleOccurrence.target_id == occurrence.target_id,
                NotificationScheduleOccurrence.occurrence_on == occurrence.occurrence_on,
            )
            .values(notification_id=notification_id)
        )
        await self._session.flush()

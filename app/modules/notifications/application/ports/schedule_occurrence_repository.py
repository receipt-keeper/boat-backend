from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.notifications.domain.schedule_occurrence import ScheduleOccurrenceKey


class ScheduleOccurrenceRepository(ABC):
    @abstractmethod
    async def reserve(self, *, occurrence: ScheduleOccurrenceKey) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def bind_notification(
        self,
        *,
        occurrence: ScheduleOccurrenceKey,
        notification_id: UUID,
    ) -> None:
        raise NotImplementedError

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule


class NotificationScheduleRuleRepository(ABC):
    @abstractmethod
    async def upsert_many(self, *, rules: Sequence[NotificationScheduleRule]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> tuple[NotificationScheduleRule, ...]:
        raise NotImplementedError

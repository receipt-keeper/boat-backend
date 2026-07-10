from collections.abc import Sequence
from uuid import UUID

from app.modules.notifications.application.ports.schedule_occurrence_repository import (
    ScheduleOccurrenceRepository,
)
from app.modules.notifications.application.ports.schedule_rule_repository import (
    NotificationScheduleRuleRepository,
)
from app.modules.notifications.domain.schedule_occurrence import ScheduleOccurrenceKey
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule


class ScheduleRuleRepositoryFake(NotificationScheduleRuleRepository):
    def __init__(self, rules: tuple[NotificationScheduleRule, ...]) -> None:
        self._rules = rules

    async def upsert_many(self, *, rules: Sequence[NotificationScheduleRule]) -> None:
        self._rules = tuple(rules)

    async def list_all(self) -> tuple[NotificationScheduleRule, ...]:
        return self._rules


class OccurrenceRepositoryFake(ScheduleOccurrenceRepository):
    def __init__(self) -> None:
        self.reserved: dict[ScheduleOccurrenceKey, UUID | None] = {}

    async def reserve(self, *, occurrence: ScheduleOccurrenceKey) -> bool:
        if occurrence in self.reserved:
            return False
        self.reserved[occurrence] = None
        return True

    async def bind_notification(
        self,
        *,
        occurrence: ScheduleOccurrenceKey,
        notification_id: UUID,
    ) -> None:
        self.reserved[occurrence] = notification_id

    def rollback_unbound(self) -> None:
        for occurrence, notification_id in tuple(self.reserved.items()):
            if notification_id is None:
                del self.reserved[occurrence]

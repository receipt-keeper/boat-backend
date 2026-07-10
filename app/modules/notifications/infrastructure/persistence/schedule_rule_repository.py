from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.ports.schedule_rule_repository import (
    NotificationScheduleRuleRepository,
)
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule
from app.modules.notifications.infrastructure.persistence import mapper
from app.modules.notifications.infrastructure.persistence.schedule_rule_orm import (
    NotificationScheduleRule as NotificationScheduleRuleRecord,
)


class SqlAlchemyNotificationScheduleRuleRepository(NotificationScheduleRuleRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, *, rules: Sequence[NotificationScheduleRule]) -> None:
        if not rules:
            return

        insert_statement = postgresql_insert(NotificationScheduleRuleRecord).values(
            [mapper.schedule_rule_to_insert_values(rule) for rule in rules]
        )
        update_columns = (
            "enabled",
            "target_kind",
            "day_offset",
            "first_delay_days",
            "repeat_interval_days",
            "lookback_days",
            "send_time_local",
            "requires_marketing_consent",
            "title_template",
            "body_template",
        )
        await self._session.execute(
            insert_statement.on_conflict_do_update(
                index_elements=[NotificationScheduleRuleRecord.campaign_key],
                set_={
                    **{
                        column_name: getattr(insert_statement.excluded, column_name)
                        for column_name in update_columns
                    },
                    "updated_at": func.now(),
                },
            )
        )
        await self._session.flush()

    async def list_all(self) -> tuple[NotificationScheduleRule, ...]:
        records = await self._session.scalars(
            select(NotificationScheduleRuleRecord).order_by(
                NotificationScheduleRuleRecord.campaign_key
            )
        )
        return tuple(mapper.schedule_rule_to_domain(record) for record in records)

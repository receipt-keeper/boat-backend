from collections.abc import AsyncIterator
from datetime import datetime

from app.modules.notifications.application.commands.create_due_notifications.command import (
    CreateDueNotificationsCommand,
)
from app.modules.notifications.application.due_notification import (
    DueNotification,
    receipt_reminder_notification,
)
from app.modules.notifications.domain.due_notification import (
    DueNotificationRule,
    matches_join_cadence,
    matches_receipt_activity,
    receipt_activity_since_for,
    registration_age_days_on,
)
from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind
from app.modules.receipts.application.queries.get_receipt_activity_for_users.query import (
    GetReceiptActivityForUsersQuery,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.result import (
    ReceiptActivity,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.use_case import (
    GetReceiptActivityForUsersQueryUseCase,
)
from app.modules.users.application.queries.list_user_registration_facts.query import (
    ListUserRegistrationFactsQuery,
    UserRegistrationFactCursor,
)
from app.modules.users.application.queries.list_user_registration_facts.result import (
    UserRegistrationFact,
)
from app.modules.users.application.queries.list_user_registration_facts.use_case import (
    ListUserRegistrationFactsQueryUseCase,
)


class ReceiptReminderNotifications:
    def __init__(
        self,
        *,
        get_receipt_activity_for_users: GetReceiptActivityForUsersQueryUseCase,
        list_user_registration_facts: ListUserRegistrationFactsQueryUseCase,
    ) -> None:
        self._get_receipt_activity_for_users = get_receipt_activity_for_users
        self._list_user_registration_facts = list_user_registration_facts

    async def iter_due_notifications(
        self,
        *,
        due_rule: DueNotificationRule,
        command: CreateDueNotificationsCommand,
    ) -> AsyncIterator[DueNotification]:
        cursor: UserRegistrationFactCursor | None = None
        while True:
            page = await self._list_user_registration_facts.execute(
                ListUserRegistrationFactsQuery(batch_size=command.batch_size, cursor=cursor)
            )
            due_facts = tuple(
                fact
                for fact in page.facts
                if matches_join_cadence(
                    rule=due_rule.rule,
                    days_since_joined=registration_age_days_on(
                        target_date=due_rule.target_date,
                        registered_at=fact.registered_at,
                    ),
                )
            )
            async for notification in self._notifications_for_facts(
                due_rule=due_rule,
                facts=due_facts,
                batch_size=command.batch_size,
            ):
                yield notification
            if page.next_cursor is None:
                return
            cursor = page.next_cursor

    async def _notifications_for_facts(
        self,
        *,
        due_rule: DueNotificationRule,
        facts: tuple[UserRegistrationFact, ...],
        batch_size: int,
    ) -> AsyncIterator[DueNotification]:
        match due_rule.rule.target_kind:
            case ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER:
                for fact in facts:
                    yield receipt_reminder_notification(due_rule=due_rule, user_id=fact.user_id)
            case (
                ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT
                | ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT
            ):
                async for activity in self._activities_for(
                    facts=facts,
                    recent_since=receipt_activity_since_for(due_rule),
                    batch_size=batch_size,
                ):
                    if matches_receipt_activity(
                        target_kind=due_rule.rule.target_kind,
                        receipt_count=activity.receipt_count,
                    ):
                        yield receipt_reminder_notification(
                            due_rule=due_rule,
                            user_id=activity.user_id,
                            receipt_count=activity.receipt_count,
                        )
            case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
                return

    async def _activities_for(
        self,
        *,
        facts: tuple[UserRegistrationFact, ...],
        recent_since: datetime | None,
        batch_size: int,
    ) -> AsyncIterator[ReceiptActivity]:
        if not facts:
            return

        cursor = None
        while True:
            page = await self._get_receipt_activity_for_users.execute(
                GetReceiptActivityForUsersQuery(
                    user_ids=tuple(fact.user_id for fact in facts),
                    limit=batch_size,
                    recent_since=recent_since,
                    cursor_user_id=cursor,
                )
            )
            for activity in page.activities:
                yield activity
            if not page.has_next:
                return
            if page.next_cursor_user_id is None:
                raise RuntimeError("영수증 활동 조회 cursor가 누락되었습니다.")
            cursor = page.next_cursor_user_id

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, assert_never

from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import ValidationError
from app.modules.notifications.application.commands.create_due_notifications.command import (
    CreateDueNotificationsCommand,
)
from app.modules.notifications.application.commands.create_due_notifications.result import (
    CreateDueNotificationRuleSummary,
    CreateDueNotificationsResult,
)
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.result import (
    CreateNotificationResult,
)
from app.modules.notifications.application.due_notification import DueNotification
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.application.ports.schedule_occurrence_repository import (
    ScheduleOccurrenceRepository,
)
from app.modules.notifications.application.ports.schedule_rule_repository import (
    NotificationScheduleRuleRepository,
)
from app.modules.notifications.application.receipt_reminder_notifications import (
    ReceiptReminderNotifications,
)
from app.modules.notifications.application.warranty_expiry_notifications import (
    WarrantyExpiryNotifications,
)
from app.modules.notifications.domain.due_notification import (
    DueNotificationRule,
    resolve_due_notification_rule,
)
from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind
from app.modules.receipts.application.queries.get_receipt_activity_for_users.use_case import (
    GetReceiptActivityForUsersQueryUseCase,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.use_case import (
    ListReceiptsExpiringOnQueryUseCase,
)
from app.modules.users.application.queries.get_existing_user_ids.use_case import (
    GetExistingUserIdsQueryUseCase,
)
from app.modules.users.application.queries.list_user_registration_facts.use_case import (
    ListUserRegistrationFactsQueryUseCase,
)

type DueNotificationAction = Literal["created", "skipped", "failed", "dry_run"]


class NotificationCreator(Protocol):
    async def create(self, command: CreateNotificationCommand) -> CreateNotificationResult: ...


@dataclass(frozen=True, slots=True)
class _RuleTotals:
    candidates: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0

    def add(self, action: DueNotificationAction) -> "_RuleTotals":
        match action:
            case "created":
                return _RuleTotals(self.candidates + 1, self.created + 1, self.skipped, self.failed)
            case "skipped":
                return _RuleTotals(self.candidates + 1, self.created, self.skipped + 1, self.failed)
            case "failed":
                return _RuleTotals(self.candidates + 1, self.created, self.skipped, self.failed + 1)
            case "dry_run":
                return _RuleTotals(self.candidates + 1, self.created, self.skipped, self.failed)
            case unreachable:
                assert_never(unreachable)


class CreateDueNotificationsCommandUseCase:
    def __init__(
        self,
        *,
        schedule_rule_repository: NotificationScheduleRuleRepository,
        occurrence_repository: ScheduleOccurrenceRepository,
        notification_repository: NotificationRepository,
        list_receipts_expiring_on: ListReceiptsExpiringOnQueryUseCase,
        get_receipt_activity_for_users: GetReceiptActivityForUsersQueryUseCase,
        list_user_registration_facts: ListUserRegistrationFactsQueryUseCase,
        get_existing_user_ids: GetExistingUserIdsQueryUseCase,
        notification_creator: NotificationCreator,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._schedule_rule_repository = schedule_rule_repository
        self._occurrence_repository = occurrence_repository
        self._notification_repository = notification_repository
        self._warranty_expiry_notifications = WarrantyExpiryNotifications(
            list_receipts_expiring_on=list_receipts_expiring_on,
            get_existing_user_ids=get_existing_user_ids,
        )
        self._receipt_reminder_notifications = ReceiptReminderNotifications(
            get_receipt_activity_for_users=get_receipt_activity_for_users,
            list_user_registration_facts=list_user_registration_facts,
        )
        self._notification_creator = notification_creator
        self._unit_of_work = unit_of_work

    async def execute(
        self,
        command: CreateDueNotificationsCommand,
    ) -> CreateDueNotificationsResult:
        try:
            summaries = await self._create_notifications(command=command)
        except Exception:
            await self._unit_of_work.rollback()
            raise
        return _result(summaries=summaries, dry_run=command.dry_run)

    async def _create_notifications(
        self,
        *,
        command: CreateDueNotificationsCommand,
    ) -> tuple[CreateDueNotificationRuleSummary, ...]:
        summaries: list[CreateDueNotificationRuleSummary] = []
        for rule in await self._schedule_rule_repository.list_all():
            if command.campaign_key is not None and rule.campaign_key != command.campaign_key:
                continue
            due_rule = resolve_due_notification_rule(
                rule=rule,
                now=command.now,
                target_date=command.target_date,
            )
            if due_rule is None:
                continue
            summaries.append(await self._create_for_rule(due_rule=due_rule, command=command))
        return tuple(summaries)

    async def _create_for_rule(
        self,
        *,
        due_rule: DueNotificationRule,
        command: CreateDueNotificationsCommand,
    ) -> CreateDueNotificationRuleSummary:
        totals = _RuleTotals()
        async for notification in self._due_notifications(due_rule=due_rule, command=command):
            totals = totals.add(
                await self._create_notification(
                    notification=notification,
                    due_rule=due_rule,
                    command=command,
                )
            )
        return CreateDueNotificationRuleSummary(
            campaign_key=due_rule.rule.campaign_key,
            candidates=totals.candidates,
            created=totals.created,
            skipped=totals.skipped,
            failed=totals.failed,
        )

    def _due_notifications(
        self,
        *,
        due_rule: DueNotificationRule,
        command: CreateDueNotificationsCommand,
    ) -> AsyncIterator[DueNotification]:
        match due_rule.rule.target_kind:
            case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
                return self._warranty_expiry_notifications.iter_due_notifications(
                    due_rule=due_rule, command=command
                )
            case (
                ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT
                | ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT
                | ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER
            ):
                return self._receipt_reminder_notifications.iter_due_notifications(
                    due_rule=due_rule, command=command
                )
            case unreachable:
                assert_never(unreachable)

    async def _create_notification(
        self,
        *,
        notification: DueNotification,
        due_rule: DueNotificationRule,
        command: CreateDueNotificationsCommand,
    ) -> DueNotificationAction:
        if await self._requires_marketing_consent(due_rule=due_rule, notification=notification):
            return "skipped"
        if command.dry_run:
            return "dry_run"
        if not await self._occurrence_repository.reserve(occurrence=notification.occurrence):
            return "skipped"
        try:
            result = await self._notification_creator.create(notification.command)
            await self._occurrence_repository.bind_notification(
                occurrence=notification.occurrence,
                notification_id=result.notification_id,
            )
            await self._unit_of_work.commit()
        except ValidationError:
            await self._unit_of_work.rollback()
            return "failed"
        return "created"

    async def _requires_marketing_consent(
        self,
        *,
        due_rule: DueNotificationRule,
        notification: DueNotification,
    ) -> bool:
        if not due_rule.rule.requires_marketing_consent:
            return False
        settings = await self._notification_repository.get_settings(
            user_id=notification.command.user_id
        )
        return not settings.marketing_consent


def _result(
    *,
    summaries: tuple[CreateDueNotificationRuleSummary, ...],
    dry_run: bool,
) -> CreateDueNotificationsResult:
    return CreateDueNotificationsResult(
        rules=summaries,
        candidates=sum(summary.candidates for summary in summaries),
        created=sum(summary.created for summary in summaries),
        skipped=sum(summary.skipped for summary in summaries),
        failed=sum(summary.failed for summary in summaries),
        dry_run=dry_run,
    )

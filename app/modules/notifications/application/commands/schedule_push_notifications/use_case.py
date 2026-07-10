from dataclasses import dataclass
from typing import Protocol, assert_never

from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import ValidationError
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.result import (
    CreateNotificationResult,
)
from app.modules.notifications.application.commands.schedule_push_notifications.command import (
    SchedulePushNotificationsCommand,
)
from app.modules.notifications.application.commands.schedule_push_notifications.result import (
    SchedulePushNotificationRuleSummary,
    SchedulePushNotificationsResult,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.application.ports.schedule_occurrence_repository import (
    ScheduleOccurrenceRepository,
)
from app.modules.notifications.application.ports.schedule_rule_repository import (
    NotificationScheduleRuleRepository,
)
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule
from app.modules.receipts.application.ports.receipt_repository import ReceiptRepository
from app.modules.users.application.ports.user_repository import UserRepository

from .candidate_streams import ScheduleCandidateStream
from .schedule_rule_due import due_schedule_rule
from .scheduler_models import (
    Accumulator,
    DueScheduleRule,
    ScheduleAction,
    ScheduleCandidate,
)


@dataclass(frozen=True, slots=True)
class ScheduleNotificationCreationError(Exception):
    campaign_key: str

    def __str__(self) -> str:
        return f"scheduled notification creation failed for {self.campaign_key}"


class NotificationCreatorPort(Protocol):
    async def create(self, command: CreateNotificationCommand) -> CreateNotificationResult: ...


class SchedulePushNotificationsCommandUseCase:
    def __init__(
        self,
        *,
        schedule_rule_repository: NotificationScheduleRuleRepository,
        occurrence_repository: ScheduleOccurrenceRepository,
        notification_repository: NotificationRepository,
        receipt_repository: ReceiptRepository,
        user_repository: UserRepository,
        notification_creator: NotificationCreatorPort,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._schedule_rule_repository = schedule_rule_repository
        self._occurrence_repository = occurrence_repository
        self._notification_repository = notification_repository
        self._candidate_stream = ScheduleCandidateStream(
            receipt_repository=receipt_repository,
            user_repository=user_repository,
        )
        self._notification_creator = notification_creator
        self._unit_of_work = unit_of_work

    async def execute(
        self,
        command: SchedulePushNotificationsCommand,
    ) -> SchedulePushNotificationsResult:
        summaries: list[SchedulePushNotificationRuleSummary] = []
        for rule in await self._rules(command):
            current_due_schedule_rule = due_schedule_rule(rule=rule, command=command)
            if current_due_schedule_rule is None:
                continue
            summary = await self._run_schedule_rule(
                due_schedule_rule=current_due_schedule_rule,
                command=command,
            )
            summaries.append(summary)

        accumulator = _accumulate(tuple(summaries))
        return SchedulePushNotificationsResult(
            rules=accumulator.rule_summaries,
            candidates=accumulator.candidates,
            created=accumulator.created,
            skipped=accumulator.skipped,
            failed=accumulator.failed,
            dry_run=command.dry_run,
        )

    async def _rules(
        self,
        command: SchedulePushNotificationsCommand,
    ) -> tuple[NotificationScheduleRule, ...]:
        rules = await self._schedule_rule_repository.list_all()
        if command.campaign_key is None:
            return rules
        return tuple(rule for rule in rules if rule.campaign_key == command.campaign_key)

    async def _run_schedule_rule(
        self,
        *,
        due_schedule_rule: DueScheduleRule,
        command: SchedulePushNotificationsCommand,
    ) -> SchedulePushNotificationRuleSummary:
        candidates = 0
        created = 0
        skipped = 0
        failed = 0
        async for candidate in self._candidate_stream.stream(
            due_schedule_rule=due_schedule_rule,
            command=command,
        ):
            candidates += 1
            action = await self._schedule_candidate(
                candidate=candidate,
                due_schedule_rule=due_schedule_rule,
                command=command,
            )
            match action:
                case "created":
                    created += 1
                case "skipped":
                    skipped += 1
                case "failed":
                    failed += 1
                case "dry_run":
                    continue
                case unreachable:
                    assert_never(unreachable)
        return SchedulePushNotificationRuleSummary(
            campaign_key=due_schedule_rule.rule.campaign_key,
            candidates=candidates,
            created=created,
            skipped=skipped,
            failed=failed,
        )

    async def _schedule_candidate(
        self,
        *,
        candidate: ScheduleCandidate,
        due_schedule_rule: DueScheduleRule,
        command: SchedulePushNotificationsCommand,
    ) -> ScheduleAction:
        if await self._should_skip_for_consent(rule=due_schedule_rule.rule, candidate=candidate):
            return "skipped"
        if command.dry_run:
            return "dry_run"
        reserved = await self._occurrence_repository.reserve(occurrence=candidate.occurrence)
        if not reserved:
            return "skipped"
        try:
            result = await self._notification_creator.create(candidate.command)
            await self._occurrence_repository.bind_notification(
                occurrence=candidate.occurrence,
                notification_id=result.notification_id,
            )
            await self._unit_of_work.commit()
            return "created"
        except (ScheduleNotificationCreationError, ValidationError):
            await self._unit_of_work.rollback()
            return "failed"

    async def _should_skip_for_consent(
        self,
        *,
        rule: NotificationScheduleRule,
        candidate: ScheduleCandidate,
    ) -> bool:
        if not rule.requires_marketing_consent:
            return False
        settings = await self._notification_repository.get_settings(
            user_id=candidate.command.user_id
        )
        return not settings.marketing_consent


def _accumulate(
    summaries: tuple[SchedulePushNotificationRuleSummary, ...],
) -> Accumulator:
    return Accumulator(
        rule_summaries=summaries,
        candidates=sum(summary.candidates for summary in summaries),
        created=sum(summary.created for summary in summaries),
        skipped=sum(summary.skipped for summary in summaries),
        failed=sum(summary.failed for summary in summaries),
    )

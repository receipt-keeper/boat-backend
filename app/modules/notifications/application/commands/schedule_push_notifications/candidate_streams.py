from collections.abc import AsyncIterator
from typing import assert_never

from app.modules.notifications.application.commands.schedule_push_notifications.command import (
    SchedulePushNotificationsCommand,
)
from app.modules.notifications.domain.schedule_rule import ScheduleRuleTargetKind
from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptRegistrationActivityQuery,
    ReceiptRepository,
    WarrantyNotificationCandidateQuery,
)
from app.modules.users.application.ports.user_repository import (
    ListUserNotificationCandidatesQuery,
    UserNotificationCandidate,
    UserRepository,
)

from .candidate_factory import (
    activity_schedule_candidate,
    engagement_schedule_candidate,
    matches_join_rule,
    warranty_schedule_candidate,
)
from .scheduler_models import DueScheduleRule, ScheduleCandidate


class ScheduleCandidateStream:
    def __init__(
        self,
        *,
        receipt_repository: ReceiptRepository,
        user_repository: UserRepository,
    ) -> None:
        self._receipt_repository = receipt_repository
        self._user_repository = user_repository

    async def stream(
        self,
        *,
        due_schedule_rule: DueScheduleRule,
        command: SchedulePushNotificationsCommand,
    ) -> AsyncIterator[ScheduleCandidate]:
        match due_schedule_rule.rule.target_kind:
            case ScheduleRuleTargetKind.WARRANTY_RECEIPT:
                async for candidate in self._warranty_candidates(
                    due_schedule_rule=due_schedule_rule,
                    command=command,
                ):
                    yield candidate
            case ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER:
                async for candidate in self._all_user_candidates(
                    due_schedule_rule=due_schedule_rule,
                    command=command,
                ):
                    yield candidate
            case (
                ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT
                | ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT
            ):
                async for candidate in self._receipt_activity_candidates(
                    due_schedule_rule=due_schedule_rule,
                    command=command,
                ):
                    yield candidate
            case unreachable:
                assert_never(unreachable)

    async def _warranty_candidates(
        self,
        *,
        due_schedule_rule: DueScheduleRule,
        command: SchedulePushNotificationsCommand,
    ) -> AsyncIterator[ScheduleCandidate]:
        offset_days = due_schedule_rule.rule.day_offset
        if offset_days is None:
            return
        cursor = None
        while True:
            page = await self._receipt_repository.list_warranty_notification_candidates(
                query=WarrantyNotificationCandidateQuery(
                    target_date=due_schedule_rule.target_date,
                    offset_days=offset_days,
                    limit=command.batch_size,
                    cursor_receipt_id=cursor,
                )
            )
            for candidate in page.candidates:
                yield warranty_schedule_candidate(
                    rule=due_schedule_rule.rule,
                    candidate=candidate,
                    occurrence_on=due_schedule_rule.target_date,
                )
            if not page.has_next:
                break
            cursor = page.next_cursor_receipt_id

    async def _all_user_candidates(
        self,
        *,
        due_schedule_rule: DueScheduleRule,
        command: SchedulePushNotificationsCommand,
    ) -> AsyncIterator[ScheduleCandidate]:
        cursor = None
        while True:
            page = await self._user_repository.list_notification_candidates(
                query=ListUserNotificationCandidatesQuery(
                    as_of=due_schedule_rule.target_date,
                    batch_size=command.batch_size,
                    cursor=cursor,
                )
            )
            for candidate in page.candidates:
                if matches_join_rule(rule=due_schedule_rule.rule, candidate=candidate):
                    yield engagement_schedule_candidate(
                        rule=due_schedule_rule.rule,
                        candidate=candidate,
                        bucket_on=due_schedule_rule.target_date,
                    )
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

    async def _receipt_activity_candidates(
        self,
        *,
        due_schedule_rule: DueScheduleRule,
        command: SchedulePushNotificationsCommand,
    ) -> AsyncIterator[ScheduleCandidate]:
        cursor = None
        while True:
            page = await self._user_repository.list_notification_candidates(
                query=ListUserNotificationCandidatesQuery(
                    as_of=due_schedule_rule.target_date,
                    batch_size=command.batch_size,
                    cursor=cursor,
                )
            )
            user_candidates = tuple(
                candidate
                for candidate in page.candidates
                if matches_join_rule(rule=due_schedule_rule.rule, candidate=candidate)
            )
            async for candidate in self._matching_receipt_activity_candidates(
                due_schedule_rule=due_schedule_rule,
                user_candidates=user_candidates,
                command=command,
            ):
                yield candidate
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

    async def _matching_receipt_activity_candidates(
        self,
        *,
        due_schedule_rule: DueScheduleRule,
        user_candidates: tuple[UserNotificationCandidate, ...],
        command: SchedulePushNotificationsCommand,
    ) -> AsyncIterator[ScheduleCandidate]:
        if not user_candidates:
            return
        activity_page = (
            await self._receipt_repository.list_receipt_registration_activity_candidates(
                query=ReceiptRegistrationActivityQuery(
                    user_ids=tuple(candidate.user_id for candidate in user_candidates),
                    target_date=due_schedule_rule.target_date,
                    limit=command.batch_size,
                    recent_days=due_schedule_rule.rule.lookback_days
                    if due_schedule_rule.rule.lookback_days is not None
                    else 1,
                )
            )
        )
        by_user = {candidate.user_id: candidate for candidate in user_candidates}
        for activity_candidate in activity_page.candidates:
            user_candidate = by_user.get(activity_candidate.user_id)
            if user_candidate is None:
                continue
            if not _matches_activity_rule(
                target_kind=due_schedule_rule.rule.target_kind,
                receipt_count=activity_candidate.receipt_count,
            ):
                continue
            yield activity_schedule_candidate(
                rule=due_schedule_rule.rule,
                user_candidate=user_candidate,
                activity_candidate=activity_candidate,
                bucket_on=due_schedule_rule.target_date,
            )


def _matches_activity_rule(
    *,
    target_kind: ScheduleRuleTargetKind,
    receipt_count: int,
) -> bool:
    match target_kind:
        case ScheduleRuleTargetKind.ENGAGEMENT_UNREGISTERED_RECEIPT:
            return receipt_count == 0
        case ScheduleRuleTargetKind.ENGAGEMENT_INACTIVE_RECEIPT:
            return receipt_count > 0
        case ScheduleRuleTargetKind.WARRANTY_RECEIPT | ScheduleRuleTargetKind.ENGAGEMENT_ALL_USER:
            return False
        case unreachable:
            assert_never(unreachable)

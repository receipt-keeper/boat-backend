from uuid import UUID

from app.core.application.event_publisher import NoOpEventPublisher
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.result import (
    CreateNotificationResult,
)
from app.modules.notifications.application.commands.create_notification.use_case import (
    NotificationCreator,
)
from app.modules.notifications.application.commands.schedule_push_notifications.use_case import (
    ScheduleNotificationCreationError,
    SchedulePushNotificationsCommandUseCase,
)
from app.modules.notifications.domain.model import NotificationSettings
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule
from app.modules.notifications.tests.scheduler_job_builders import NOW
from app.modules.notifications.tests.scheduler_job_candidate_repositories import (
    ReceiptRepositoryFake,
    UnitOfWorkFake,
    UserRepositoryFake,
)
from app.modules.notifications.tests.scheduler_job_notification_repository import (
    NotificationRepositoryFake,
)
from app.modules.notifications.tests.scheduler_job_occurrence_repositories import (
    OccurrenceRepositoryFake,
    ScheduleRuleRepositoryFake,
)
from app.modules.receipts.application.ports.receipt_repository import (
    ReceiptRegistrationActivityCandidate,
    WarrantyNotificationCandidate,
)
from app.modules.users.application.ports.user_repository import UserNotificationCandidate


class FailingNotificationCreator:
    async def create(self, command: CreateNotificationCommand) -> CreateNotificationResult:
        raise ScheduleNotificationCreationError(campaign_key=command.kind)


class SchedulerFixture:
    def __init__(
        self,
        *,
        rules: tuple[NotificationScheduleRule, ...],
        warranty_candidates: tuple[WarrantyNotificationCandidate, ...] = (),
        user_candidates: tuple[UserNotificationCandidate, ...] = (),
        receipt_activity_candidates: tuple[ReceiptRegistrationActivityCandidate, ...] = (),
        settings: dict[UUID, NotificationSettings] | None = None,
        fail_creates: bool = False,
    ) -> None:
        self.schedule_rule_repository = ScheduleRuleRepositoryFake(rules)
        self.occurrence_repository = OccurrenceRepositoryFake()
        self.notification_repository = NotificationRepositoryFake(settings or {})
        self.receipt_repository = ReceiptRepositoryFake(
            warranty_candidates=warranty_candidates,
            receipt_activity_candidates=receipt_activity_candidates,
        )
        self.user_repository = UserRepositoryFake(user_candidates)
        self.unit_of_work = UnitOfWorkFake(self.occurrence_repository.rollback_unbound)
        self.fail_creates = fail_creates
        self.use_case = self.fresh_use_case()

    def fresh_use_case(self) -> SchedulePushNotificationsCommandUseCase:
        notification_creator = (
            FailingNotificationCreator()
            if self.fail_creates
            else NotificationCreator(
                notification_repository=self.notification_repository,
                event_publisher=NoOpEventPublisher(),
                clock=lambda: NOW,
            )
        )
        return SchedulePushNotificationsCommandUseCase(
            schedule_rule_repository=self.schedule_rule_repository,
            occurrence_repository=self.occurrence_repository,
            notification_repository=self.notification_repository,
            receipt_repository=self.receipt_repository,
            user_repository=self.user_repository,
            notification_creator=notification_creator,
            unit_of_work=self.unit_of_work,
        )

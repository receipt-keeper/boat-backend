from collections.abc import Callable
from uuid import UUID

from app.core.application.event_publisher import NoOpEventPublisher
from app.modules.notifications.application.commands.create_due_notifications.use_case import (
    CreateDueNotificationsCommandUseCase,
)
from app.modules.notifications.application.commands.create_notification.use_case import (
    NotificationCreator,
)
from app.modules.notifications.domain.model import NotificationSettings
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule
from app.modules.notifications.tests.due_notification_query_fakes import (
    ExistingUserIdsReaderFake,
    ExpiringReceiptsReaderFake,
    ReceiptActivityForUsersReaderFake,
    UserRegistrationFactsReaderFake,
)
from app.modules.notifications.tests.scheduler_job_builders import NOW
from app.modules.notifications.tests.scheduler_job_notification_repository import (
    NotificationRepositoryFake,
)
from app.modules.notifications.tests.scheduler_job_occurrence_repositories import (
    OccurrenceRepositoryFake,
    ScheduleRuleRepositoryFake,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.result import (
    ReceiptActivity,
)
from app.modules.receipts.application.queries.get_receipt_activity_for_users.use_case import (
    GetReceiptActivityForUsersQueryUseCase,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.result import (
    ExpiringReceipt,
)
from app.modules.receipts.application.queries.list_receipts_expiring_on.use_case import (
    ListReceiptsExpiringOnQueryUseCase,
)
from app.modules.users.application.queries.get_existing_user_ids.use_case import (
    GetExistingUserIdsQueryUseCase,
)
from app.modules.users.application.queries.list_user_registration_facts.result import (
    UserRegistrationFact,
)
from app.modules.users.application.queries.list_user_registration_facts.use_case import (
    ListUserRegistrationFactsQueryUseCase,
)


class UnitOfWorkFake:
    def __init__(self, rollback_hook: Callable[[], None] | None = None) -> None:
        self.commits = 0
        self.rollbacks = 0
        self._rollback_hook = rollback_hook

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self._rollback_hook is not None:
            self._rollback_hook()


class SchedulerFixture:
    def __init__(
        self,
        *,
        rules: tuple[NotificationScheduleRule, ...],
        warranty_candidates: tuple[ExpiringReceipt, ...] = (),
        user_candidates: tuple[UserRegistrationFact, ...] = (),
        receipt_activity_candidates: tuple[ReceiptActivity, ...] = (),
        existing_user_ids: frozenset[UUID] | None = None,
        settings: dict[UUID, NotificationSettings] | None = None,
        notification_create_exception: Exception | None = None,
        notification_create_exceptions: list[Exception | None] | None = None,
    ) -> None:
        self.schedule_rule_repository = ScheduleRuleRepositoryFake(rules)
        self.occurrence_repository = OccurrenceRepositoryFake()
        self.notification_repository = NotificationRepositoryFake(
            settings or {},
            create_exception=notification_create_exception,
            create_exceptions=notification_create_exceptions,
        )
        self.expiring_receipts_reader = ExpiringReceiptsReaderFake(warranty_candidates)
        self.existing_user_ids_reader = ExistingUserIdsReaderFake(
            existing_user_ids
            if existing_user_ids is not None
            else frozenset(candidate.user_id for candidate in warranty_candidates)
        )
        self.receipt_activity_reader = ReceiptActivityForUsersReaderFake(
            receipt_activity_candidates
        )
        self.user_registration_facts_reader = UserRegistrationFactsReaderFake(user_candidates)
        self.unit_of_work = UnitOfWorkFake(self.occurrence_repository.rollback_unbound)
        self.use_case = self.fresh_use_case()

    def fresh_use_case(self) -> CreateDueNotificationsCommandUseCase:
        notification_creator = NotificationCreator(
            notification_repository=self.notification_repository,
            event_publisher=NoOpEventPublisher(),
            clock=lambda: NOW,
        )
        return CreateDueNotificationsCommandUseCase(
            schedule_rule_repository=self.schedule_rule_repository,
            occurrence_repository=self.occurrence_repository,
            list_receipts_expiring_on=ListReceiptsExpiringOnQueryUseCase(
                reader=self.expiring_receipts_reader
            ),
            get_receipt_activity_for_users=GetReceiptActivityForUsersQueryUseCase(
                reader=self.receipt_activity_reader
            ),
            list_user_registration_facts=ListUserRegistrationFactsQueryUseCase(
                reader=self.user_registration_facts_reader
            ),
            get_existing_user_ids=GetExistingUserIdsQueryUseCase(
                reader=self.existing_user_ids_reader
            ),
            notification_creator=notification_creator,
            unit_of_work=self.unit_of_work,
        )

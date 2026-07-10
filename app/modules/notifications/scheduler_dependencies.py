from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.modules.notifications.application.commands.create_notification.use_case import (
    NotificationCreator,
)
from app.modules.notifications.application.commands.schedule_push_notifications.use_case import (
    SchedulePushNotificationsCommandUseCase,
)
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyNotificationScheduleRuleRepository,
    SqlAlchemyScheduleOccurrenceRepository,
)
from app.modules.notifications.push_dependencies import build_notification_event_registry
from app.modules.receipts.dependencies import build_receipt_repository
from app.modules.users.dependencies import build_user_repository


def build_schedule_push_notifications_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> SchedulePushNotificationsCommandUseCase:
    event_publisher = OutboxEventPublisher(
        session=session,
        registry=build_notification_event_registry(),
    )
    notification_creator = NotificationCreator(
        notification_repository=SqlAlchemyNotificationRepository(session),
        event_publisher=event_publisher,
    )
    return SchedulePushNotificationsCommandUseCase(
        schedule_rule_repository=SqlAlchemyNotificationScheduleRuleRepository(session),
        occurrence_repository=SqlAlchemyScheduleOccurrenceRepository(session),
        notification_repository=SqlAlchemyNotificationRepository(session),
        receipt_repository=build_receipt_repository(session),
        user_repository=build_user_repository(session),
        notification_creator=notification_creator,
        unit_of_work=unit_of_work,
    )

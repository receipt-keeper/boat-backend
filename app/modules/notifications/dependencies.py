from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.event_publisher import EventPublisher, NoOpEventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.notifications.application.commands.create_due_notifications.use_case import (
    CreateDueNotificationsCommandUseCase,
)
from app.modules.notifications.application.commands.create_notification.use_case import (
    CreateNotificationCommandUseCase,
    NotificationCreator,
)
from app.modules.notifications.application.commands.delete_user_push_tokens.use_case import (
    DeleteUserPushTokensCommandUseCase,
)
from app.modules.notifications.application.commands.mark_notification_read.use_case import (
    MarkNotificationReadCommandUseCase,
)
from app.modules.notifications.application.commands.register_device_token.use_case import (
    RegisterDeviceTokenCommandUseCase,
)
from app.modules.notifications.application.commands.unregister_device_token.use_case import (
    UnregisterDeviceTokenCommandUseCase,
)
from app.modules.notifications.application.commands.update_notification_settings.use_case import (
    UpdateNotificationSettingsCommandUseCase,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)
from app.modules.notifications.application.queries.get_notification_settings.use_case import (
    GetNotificationSettingsQueryUseCase,
)
from app.modules.notifications.application.queries.list_notifications.use_case import (
    ListNotificationsQueryUseCase,
)
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyNotificationScheduleRuleRepository,
    SqlAlchemyPushTokenRepository,
    SqlAlchemyScheduleOccurrenceRepository,
)
from app.modules.notifications.push_dependencies import (
    NotificationPushDispatcher,
    build_notification_event_dispatcher,
    build_notification_event_registry,
    build_notification_outbox_relay,
    get_notification_event_publisher,
    get_notification_push_dispatcher,
    get_push_sender,
)
from app.modules.receipts.dependencies import (
    build_get_receipt_activity_for_users_query_use_case,
    build_list_receipts_expiring_on_query_use_case,
)
from app.modules.users.dependencies import build_list_user_registration_facts_query_use_case

__all__ = (
    "NotificationPushDispatcher",
    "build_create_due_notifications_command_use_case",
    "build_notification_event_dispatcher",
    "build_notification_event_registry",
    "build_notification_outbox_relay",
    "get_notification_push_dispatcher",
    "get_push_sender",
)


async def get_notification_repository(session: AsyncSessionDep) -> NotificationRepository:
    return SqlAlchemyNotificationRepository(session)


async def get_push_token_repository(session: AsyncSessionDep) -> PushTokenRepository:
    return SqlAlchemyPushTokenRepository(session)


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def build_create_due_notifications_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> CreateDueNotificationsCommandUseCase:
    notification_repository = SqlAlchemyNotificationRepository(session)
    notification_creator = NotificationCreator(
        notification_repository=notification_repository,
        event_publisher=OutboxEventPublisher(
            session=session,
            registry=build_notification_event_registry(),
        ),
    )
    return CreateDueNotificationsCommandUseCase(
        schedule_rule_repository=SqlAlchemyNotificationScheduleRuleRepository(session),
        occurrence_repository=SqlAlchemyScheduleOccurrenceRepository(session),
        notification_repository=notification_repository,
        list_receipts_expiring_on=build_list_receipts_expiring_on_query_use_case(session),
        get_receipt_activity_for_users=build_get_receipt_activity_for_users_query_use_case(session),
        list_user_registration_facts=build_list_user_registration_facts_query_use_case(session),
        notification_creator=notification_creator,
        unit_of_work=unit_of_work,
    )


def build_update_notification_settings_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> UpdateNotificationSettingsCommandUseCase:
    return UpdateNotificationSettingsCommandUseCase(
        notification_repository=SqlAlchemyNotificationRepository(session),
        unit_of_work=unit_of_work,
    )


def build_delete_user_push_tokens_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> DeleteUserPushTokensCommandUseCase:
    return DeleteUserPushTokensCommandUseCase(
        push_token_repository=SqlAlchemyPushTokenRepository(session),
        unit_of_work=unit_of_work,
    )


async def get_create_notification_command_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
    event_publisher: Annotated[EventPublisher, Depends(get_notification_event_publisher)],
) -> CreateNotificationCommandUseCase:
    return CreateNotificationCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
        event_publisher=event_publisher,
    )


async def get_test_notification_create_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> CreateNotificationCommandUseCase:
    """이벤트 미발행 — example 테스트 보조용.

    example 모듈의 테스트 푸시 API가 표준 생성 경로(및 그에 연쇄되는
    background 푸시 발송)와 이중 발송되지 않도록, 이벤트를 발행하지 않는
    `NoOpEventPublisher`로 조립한 `CreateNotificationCommandUseCase`를
    제공한다. 표준 `POST /notifications` 경로에서는 사용하지 않는다.
    """
    return CreateNotificationCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
        event_publisher=NoOpEventPublisher(),
    )


async def get_mark_notification_read_command_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> MarkNotificationReadCommandUseCase:
    return MarkNotificationReadCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
    )


async def get_update_notification_settings_command_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UpdateNotificationSettingsCommandUseCase:
    return UpdateNotificationSettingsCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
    )


async def get_list_notifications_query_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
) -> ListNotificationsQueryUseCase:
    return ListNotificationsQueryUseCase(notification_repository=notification_repository)


async def get_notification_settings_query_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
) -> GetNotificationSettingsQueryUseCase:
    return GetNotificationSettingsQueryUseCase(
        notification_repository=notification_repository,
    )


async def get_register_device_token_command_use_case(
    push_token_repository: Annotated[
        PushTokenRepository,
        Depends(get_push_token_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> RegisterDeviceTokenCommandUseCase:
    return RegisterDeviceTokenCommandUseCase(
        push_token_repository=push_token_repository,
        unit_of_work=unit_of_work,
    )


async def get_unregister_device_token_command_use_case(
    push_token_repository: Annotated[
        PushTokenRepository,
        Depends(get_push_token_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> UnregisterDeviceTokenCommandUseCase:
    return UnregisterDeviceTokenCommandUseCase(
        push_token_repository=push_token_repository,
        unit_of_work=unit_of_work,
    )


CreateNotificationCommandUseCaseDep = Annotated[
    CreateNotificationCommandUseCase,
    Depends(get_create_notification_command_use_case),
]
MarkNotificationReadCommandUseCaseDep = Annotated[
    MarkNotificationReadCommandUseCase,
    Depends(get_mark_notification_read_command_use_case),
]
UpdateNotificationSettingsCommandUseCaseDep = Annotated[
    UpdateNotificationSettingsCommandUseCase,
    Depends(get_update_notification_settings_command_use_case),
]
ListNotificationsQueryUseCaseDep = Annotated[
    ListNotificationsQueryUseCase,
    Depends(get_list_notifications_query_use_case),
]
GetNotificationSettingsQueryUseCaseDep = Annotated[
    GetNotificationSettingsQueryUseCase,
    Depends(get_notification_settings_query_use_case),
]
RegisterDeviceTokenCommandUseCaseDep = Annotated[
    RegisterDeviceTokenCommandUseCase,
    Depends(get_register_device_token_command_use_case),
]
UnregisterDeviceTokenCommandUseCaseDep = Annotated[
    UnregisterDeviceTokenCommandUseCase,
    Depends(get_unregister_device_token_command_use_case),
]

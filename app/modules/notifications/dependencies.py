from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.notifications.application.commands.create_notification.use_case import (
    CreateNotificationCommandUseCase,
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
    SqlAlchemyPushTokenRepository,
)


async def get_notification_repository(session: AsyncSessionDep) -> NotificationRepository:
    return SqlAlchemyNotificationRepository(session)


async def get_push_token_repository(session: AsyncSessionDep) -> PushTokenRepository:
    return SqlAlchemyPushTokenRepository(session)


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def build_update_notification_settings_command_use_case(
    session: AsyncSession,
    unit_of_work: UnitOfWork,
) -> UpdateNotificationSettingsCommandUseCase:
    return UpdateNotificationSettingsCommandUseCase(
        notification_repository=SqlAlchemyNotificationRepository(session),
        unit_of_work=unit_of_work,
    )


async def get_create_notification_command_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
    unit_of_work: Annotated[UnitOfWork, Depends(get_unit_of_work)],
) -> CreateNotificationCommandUseCase:
    return CreateNotificationCommandUseCase(
        notification_repository=notification_repository,
        unit_of_work=unit_of_work,
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

from typing import Annotated

from fastapi import Depends

from app.core.application.unit_of_work import UnitOfWork
from app.core.db.session import AsyncSessionDep
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.notifications.application.commands.create_notification.use_case import (
    CreateNotificationCommandUseCase,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.application.queries.list_notifications.use_case import (
    ListNotificationsQueryUseCase,
)
from app.modules.notifications.infrastructure.persistence.repository import (
    SqlAlchemyNotificationRepository,
)


async def get_notification_repository(session: AsyncSessionDep) -> NotificationRepository:
    return SqlAlchemyNotificationRepository(session)


async def get_unit_of_work(session: AsyncSessionDep) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


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


async def get_list_notifications_query_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
) -> ListNotificationsQueryUseCase:
    return ListNotificationsQueryUseCase(notification_repository=notification_repository)


CreateNotificationCommandUseCaseDep = Annotated[
    CreateNotificationCommandUseCase,
    Depends(get_create_notification_command_use_case),
]
ListNotificationsQueryUseCaseDep = Annotated[
    ListNotificationsQueryUseCase,
    Depends(get_list_notifications_query_use_case),
]

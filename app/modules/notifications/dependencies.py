from typing import Annotated

from fastapi import Depends

from app.core.db.session import AsyncSessionDep
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


async def get_list_notifications_query_use_case(
    notification_repository: Annotated[
        NotificationRepository,
        Depends(get_notification_repository),
    ],
) -> ListNotificationsQueryUseCase:
    return ListNotificationsQueryUseCase(notification_repository=notification_repository)


ListNotificationsQueryUseCaseDep = Annotated[
    ListNotificationsQueryUseCase,
    Depends(get_list_notifications_query_use_case),
]

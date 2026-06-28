from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.application.queries.get_notification_settings.query import (
    GetNotificationSettingsQuery,
)
from app.modules.notifications.application.queries.get_notification_settings.result import (
    GetNotificationSettingsResult,
)


class GetNotificationSettingsQueryUseCase:
    def __init__(self, *, notification_repository: NotificationRepository) -> None:
        self._notification_repository = notification_repository

    async def execute(
        self,
        query: GetNotificationSettingsQuery,
    ) -> GetNotificationSettingsResult:
        settings = await self._notification_repository.get_settings(user_id=query.user_id)
        return GetNotificationSettingsResult(
            push_enabled=settings.push_enabled,
            marketing_consent=settings.marketing_consent,
        )

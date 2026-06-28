from app.core.application.unit_of_work import UnitOfWork
from app.modules.notifications.application.commands.update_notification_settings.command import (
    UpdateNotificationSettingsCommand,
)
from app.modules.notifications.application.commands.update_notification_settings.result import (
    UpdateNotificationSettingsResult,
)
from app.modules.notifications.application.ports.notification_repository import (
    NotificationRepository,
)
from app.modules.notifications.domain.model import NotificationSettings


class UpdateNotificationSettingsCommandUseCase:
    def __init__(
        self,
        *,
        notification_repository: NotificationRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._notification_repository = notification_repository
        self._unit_of_work = unit_of_work

    async def execute(
        self,
        command: UpdateNotificationSettingsCommand,
    ) -> UpdateNotificationSettingsResult:
        current = await self._notification_repository.get_settings(user_id=command.user_id)
        updated = NotificationSettings.create(
            user_id=command.user_id,
            push_enabled=(
                current.push_enabled if command.push_enabled is None else command.push_enabled
            ),
            marketing_consent=(
                current.marketing_consent
                if command.marketing_consent is None
                else command.marketing_consent
            ),
        )
        settings = await self._notification_repository.update_settings(
            settings=updated,
        )
        await self._unit_of_work.commit()
        return UpdateNotificationSettingsResult(
            push_enabled=settings.push_enabled,
            marketing_consent=settings.marketing_consent,
        )

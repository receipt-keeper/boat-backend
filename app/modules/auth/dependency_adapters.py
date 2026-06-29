from uuid import UUID

from fastapi import Request

from app.core.db.session import request_async_session
from app.modules.auth.application.ports.credential_repository import ActiveSessionChecker
from app.modules.auth.application.ports.notification_settings_initializer import (
    NotificationSettingsInitializer,
)
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.notifications.application.commands.update_notification_settings.command import (
    UpdateNotificationSettingsCommand,
)
from app.modules.notifications.application.commands.update_notification_settings.use_case import (
    UpdateNotificationSettingsCommandUseCase,
)


class NotificationSettingsInitializerAdapter(NotificationSettingsInitializer):
    def __init__(self, command_use_case: UpdateNotificationSettingsCommandUseCase) -> None:
        self._command_use_case = command_use_case

    async def initialize(self, *, user_id: UUID, marketing_consent: bool) -> None:
        await self._command_use_case.execute(
            UpdateNotificationSettingsCommand(
                user_id=user_id,
                marketing_consent=marketing_consent,
            )
        )


class RequestActiveSessionChecker(ActiveSessionChecker):
    def __init__(self, request: Request) -> None:
        self._request = request

    async def exists_active_session(
        self,
        *,
        user_id: UUID,
        credentials_id: UUID,
        session_id: UUID,
    ) -> bool:
        async with request_async_session(self._request) as session:
            return await SqlAlchemyCredentialRepository(session).exists_active_session(
                user_id=user_id,
                credentials_id=credentials_id,
                session_id=session_id,
            )

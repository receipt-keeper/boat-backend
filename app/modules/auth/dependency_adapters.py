from uuid import UUID

from fastapi import Request

from app.core.db.session import request_async_session
from app.modules.auth.application.ports.credential_repository import ActiveSessionChecker
from app.modules.auth.application.ports.credit_lifecycle import (
    CreditInitializer,
    CreditWithdrawalCleaner,
)
from app.modules.auth.application.ports.notification_settings_initializer import (
    NotificationSettingsInitializer,
)
from app.modules.auth.application.ports.push_token_lifecycle import (
    PushTokenWithdrawalCleaner,
)
from app.modules.auth.infrastructure.persistence.credential_repository import (
    SqlAlchemyCredentialRepository,
)
from app.modules.credits.application.commands.delete_user_credits.command import (
    DeleteUserCreditsCommand,
)
from app.modules.credits.application.commands.delete_user_credits.use_case import (
    DeleteUserCreditsCommandUseCase,
)
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.application.commands.grant_credit.use_case import GrantCreditCommandUseCase
from app.modules.credits.domain import CreditAmount, CreditReason
from app.modules.notifications.application.commands.delete_user_push_tokens.command import (
    DeleteUserPushTokensCommand,
)
from app.modules.notifications.application.commands.delete_user_push_tokens.use_case import (
    DeleteUserPushTokensCommandUseCase,
)
from app.modules.notifications.application.commands.update_notification_settings.command import (
    UpdateNotificationSettingsCommand,
)
from app.modules.notifications.application.commands.update_notification_settings.use_case import (
    UpdateNotificationSettingsCommandUseCase,
)

_INITIAL_MONTHLY_OCR_CREDIT_COUNT = 5


class CreditInitializerAdapter(CreditInitializer):
    def __init__(self, command_use_case: GrantCreditCommandUseCase) -> None:
        self._command_use_case = command_use_case

    async def initialize(self, *, user_id: UUID) -> None:
        await self._command_use_case.execute(
            GrantCreditCommand(
                user_id=user_id,
                amount=CreditAmount(value=_INITIAL_MONTHLY_OCR_CREDIT_COUNT),
                reason=CreditReason.MONTHLY_OCR_ALLOWANCE,
            )
        )


class CreditWithdrawalCleanerAdapter(CreditWithdrawalCleaner):
    def __init__(self, command_use_case: DeleteUserCreditsCommandUseCase) -> None:
        self._command_use_case = command_use_case

    async def delete_account_state(self, *, user_id: UUID) -> None:
        await self._command_use_case.execute(DeleteUserCreditsCommand(user_id=user_id))


class PushTokenWithdrawalCleanerAdapter(PushTokenWithdrawalCleaner):
    def __init__(self, command_use_case: DeleteUserPushTokensCommandUseCase) -> None:
        self._command_use_case = command_use_case

    async def delete_account_state(self, *, user_id: UUID) -> None:
        await self._command_use_case.execute(DeleteUserPushTokensCommand(user_id=user_id))


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

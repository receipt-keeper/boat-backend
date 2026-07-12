from collections.abc import Sequence
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
from app.modules.credits.application.commands.close_credit_account.command import (
    CloseCreditsAccountCommand,
)
from app.modules.credits.application.commands.close_credit_account.use_case import (
    CloseCreditsAccountCommandUseCase,
)
from app.modules.credits.application.commands.issue_signup_allowance.command import (
    IssueSignupAllowanceCommand,
)
from app.modules.credits.application.commands.issue_signup_allowance.use_case import (
    IssueSignupAllowanceCommandUseCase,
)
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


class CreditInitializerAdapter(CreditInitializer):
    """가입 보너스 지급/재활성화 정책은 credits가 소유한다 - 이 어댑터는 auth가 계산한
    handle을 그대로 전달할 뿐, 수량/reason/idempotency 전략은 갖지 않는다."""

    def __init__(self, command_use_case: IssueSignupAllowanceCommandUseCase) -> None:
        self._command_use_case = command_use_case

    async def initialize(
        self,
        *,
        user_id: UUID,
        subject_handle: str,
        candidate_handles: Sequence[str],
    ) -> None:
        await self._command_use_case.execute(
            IssueSignupAllowanceCommand(
                user_id=user_id,
                subject_handle=subject_handle,
                candidate_handles=candidate_handles,
            )
        )


class CreditWithdrawalCleanerAdapter(CreditWithdrawalCleaner):
    def __init__(self, command_use_case: CloseCreditsAccountCommandUseCase) -> None:
        self._command_use_case = command_use_case

    async def delete_account_state(
        self,
        *,
        user_id: UUID,
        candidate_handles: Sequence[str],
    ) -> None:
        await self._command_use_case.execute(
            CloseCreditsAccountCommand(user_id=user_id, candidate_handles=candidate_handles)
        )


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

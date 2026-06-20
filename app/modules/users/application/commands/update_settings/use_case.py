from app.core.domain.exceptions import NotFoundError
from app.modules.users.application.commands.update_settings.command import UpdateSettingsCommand
from app.modules.users.application.commands.update_settings.result import UpdateSettingsResult
from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.domain.model import UserSettings


class UpdateSettingsCommandUseCase:
    def __init__(self, *, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def execute(self, command: UpdateSettingsCommand) -> UpdateSettingsResult:
        state = await self._user_repository.find_account_state(user_id=command.user_id)
        if state is None:
            raise NotFoundError("사용자를 찾을 수 없습니다.")

        current = state.settings
        notification_enabled = (
            current.notification_enabled
            if command.notification_enabled is None
            else command.notification_enabled
        )
        marketing_consent = (
            current.marketing_consent
            if command.marketing_consent is None
            else command.marketing_consent
        )
        settings = await self._user_repository.update_settings(
            settings=UserSettings.create(
                user_id=command.user_id,
                notification_enabled=notification_enabled,
                marketing_consent=marketing_consent,
                terms_version=current.terms_version,
                privacy_version=current.privacy_version,
                terms_accepted_at=current.terms_accepted_at,
                privacy_accepted_at=current.privacy_accepted_at,
                marketing_consent_updated_at=current.marketing_consent_updated_at,
            )
        )
        return UpdateSettingsResult(
            user_id=settings.id,
            notification_enabled=settings.notification_enabled,
            marketing_consent=settings.marketing_consent,
        )

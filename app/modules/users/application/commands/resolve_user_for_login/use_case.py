from datetime import UTC, datetime

from app.core.domain.exceptions import ErrorDetail, NotFoundError, ValidationError
from app.modules.users.application.commands.resolve_user_for_login.command import (
    ResolveUserForLoginCommand,
)
from app.modules.users.application.commands.resolve_user_for_login.result import (
    ResolveUserForLoginResult,
)
from app.modules.users.application.ports.user_repository import (
    CreateUserAccountState,
    UserAccountState,
    UserRepository,
)
from app.modules.users.domain.model import NormalizedEmail, User, UserEntitlement, UserSettings


class ResolveUserForLoginCommandUseCase:
    def __init__(self, *, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def execute(self, command: ResolveUserForLoginCommand) -> ResolveUserForLoginResult:
        normalized_email = NormalizedEmail(command.email.strip().lower())
        existing_user = await self._user_repository.find_user_by_normalized_email(
            normalized_email=normalized_email.value
        )
        if existing_user is not None:
            existing_state = await self._user_repository.find_account_state(
                user_id=existing_user.id
            )
            if existing_state is not None:
                return _resolve_result(existing_state)

        _require_consent(command)
        accepted_at = datetime.now(UTC)
        user = User.create(
            name=command.name,
            email=command.email.strip(),
            normalized_email=normalized_email.value,
            profile_image_url=command.profile_image_url,
        )
        state = await self._user_repository.create_account_state(
            state=CreateUserAccountState(
                user=user,
                settings=UserSettings.create(
                    user_id=user.id,
                    marketing_consent=command.marketing_consent,
                    terms_version=command.terms_version,
                    privacy_version=command.privacy_version,
                    terms_accepted_at=accepted_at if command.terms_accepted else None,
                    privacy_accepted_at=accepted_at if command.privacy_accepted else None,
                    marketing_consent_updated_at=(
                        accepted_at if command.marketing_consent else None
                    ),
                ),
                entitlement=UserEntitlement.create(
                    user_id=user.id,
                    free_analysis_tokens_remaining=command.initial_free_analysis_tokens,
                ),
            )
        )
        return _resolve_result(state)


def _require_consent(command: ResolveUserForLoginCommand) -> None:
    details: list[ErrorDetail] = []
    if not command.terms_accepted:
        details.append(
            ErrorDetail(field="termsAccepted", message="이용약관에 동의해야 가입할 수 있습니다.")
        )
    if not command.privacy_accepted:
        details.append(
            ErrorDetail(
                field="privacyAccepted",
                message="개인정보 처리방침에 동의해야 가입할 수 있습니다.",
            )
        )
    if details:
        raise ValidationError(details)


def _resolve_result(state: UserAccountState) -> ResolveUserForLoginResult:
    if state.user.normalized_email is None:
        raise NotFoundError("정규화된 이메일 사용자를 찾을 수 없습니다.")
    return ResolveUserForLoginResult(
        user_id=state.user.id,
        normalized_email=state.user.normalized_email.value,
        notification_enabled=state.settings.notification_enabled,
        marketing_consent=state.settings.marketing_consent,
        free_analysis_tokens_remaining=state.entitlement.free_analysis_tokens_remaining.value,
    )

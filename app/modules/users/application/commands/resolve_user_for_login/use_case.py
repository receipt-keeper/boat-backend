from datetime import UTC, datetime
from typing import Final

from app.core.application.unit_of_work import UnitOfWork
from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.modules.users.application.commands.resolve_user_for_login.command import (
    ResolveUserForLoginCommand,
)
from app.modules.users.application.commands.resolve_user_for_login.result import (
    ResolveUserForLoginResult,
)
from app.modules.users.application.ports.user_repository import (
    CreateUserAccountState,
    UserRepository,
)
from app.modules.users.domain.model import User, UserSettings

MAX_CONSENT_VERSION_LENGTH: Final = 50


class ResolveUserForLoginCommandUseCase:
    def __init__(self, *, user_repository: UserRepository, unit_of_work: UnitOfWork) -> None:
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: ResolveUserForLoginCommand) -> ResolveUserForLoginResult:
        terms_version = _normalized_consent_version(command.terms_version)
        privacy_version = _normalized_consent_version(command.privacy_version)
        _require_consent(
            command,
            terms_version=terms_version,
            privacy_version=privacy_version,
        )
        accepted_at = datetime.now(UTC)
        user = User.create(
            name=command.name,
            email=command.email,
            profile_image_url=command.profile_image_url,
        )
        state = await self._user_repository.create_account_state(
            state=CreateUserAccountState(
                user=user,
                settings=UserSettings.create(
                    user_id=user.id,
                    terms_version=terms_version,
                    privacy_version=privacy_version,
                    terms_accepted_at=accepted_at if command.terms_accepted else None,
                    privacy_accepted_at=accepted_at if command.privacy_accepted else None,
                ),
            )
        )
        await self._unit_of_work.commit()
        return ResolveUserForLoginResult(user_id=state.user.id)


def _require_consent(
    command: ResolveUserForLoginCommand,
    *,
    terms_version: str | None,
    privacy_version: str | None,
) -> None:
    details: list[ErrorDetail] = []
    if not command.terms_accepted:
        details.append(
            ErrorDetail(field="termsAccepted", message="이용약관에 동의해야 가입할 수 있습니다.")
        )
    if command.terms_accepted and terms_version is None:
        details.append(
            ErrorDetail(field="termsVersion", message="동의한 이용약관 버전이 필요합니다.")
        )
    if (
        command.terms_accepted
        and terms_version is not None
        and len(terms_version) > MAX_CONSENT_VERSION_LENGTH
    ):
        details.append(
            ErrorDetail(
                field="termsVersion",
                message="동의한 이용약관 버전은 50자 이하여야 합니다.",
            )
        )
    if not command.privacy_accepted:
        details.append(
            ErrorDetail(
                field="privacyAccepted",
                message="개인정보 처리방침에 동의해야 가입할 수 있습니다.",
            )
        )
    if command.privacy_accepted and privacy_version is None:
        details.append(
            ErrorDetail(
                field="privacyVersion", message="동의한 개인정보 처리방침 버전이 필요합니다."
            )
        )
    if (
        command.privacy_accepted
        and privacy_version is not None
        and len(privacy_version) > MAX_CONSENT_VERSION_LENGTH
    ):
        details.append(
            ErrorDetail(
                field="privacyVersion",
                message="동의한 개인정보 처리방침 버전은 50자 이하여야 합니다.",
            )
        )
    if details:
        raise ValidationError(details)


def _normalized_consent_version(version: str | None) -> str | None:
    if version is None:
        return None

    normalized = version.strip()
    if normalized == "":
        return None
    return normalized

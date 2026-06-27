from datetime import UTC, datetime

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


class ResolveUserForLoginCommandUseCase:
    def __init__(self, *, user_repository: UserRepository, unit_of_work: UnitOfWork) -> None:
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: ResolveUserForLoginCommand) -> ResolveUserForLoginResult:
        _require_consent(command)
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
                    terms_version=command.terms_version,
                    privacy_version=command.privacy_version,
                    terms_accepted_at=accepted_at if command.terms_accepted else None,
                    privacy_accepted_at=accepted_at if command.privacy_accepted else None,
                ),
            )
        )
        await self._unit_of_work.commit()
        return ResolveUserForLoginResult(user_id=state.user.id)


def _require_consent(command: ResolveUserForLoginCommand) -> None:
    details: list[ErrorDetail] = []
    if not command.terms_accepted:
        details.append(
            ErrorDetail(field="termsAccepted", message="이용약관에 동의해야 가입할 수 있습니다.")
        )
    if command.terms_accepted and command.terms_version is None:
        details.append(
            ErrorDetail(field="termsVersion", message="동의한 이용약관 버전이 필요합니다.")
        )
    if not command.privacy_accepted:
        details.append(
            ErrorDetail(
                field="privacyAccepted",
                message="개인정보 처리방침에 동의해야 가입할 수 있습니다.",
            )
        )
    if command.privacy_accepted and command.privacy_version is None:
        details.append(
            ErrorDetail(
                field="privacyVersion", message="동의한 개인정보 처리방침 버전이 필요합니다."
            )
        )
    if details:
        raise ValidationError(details)

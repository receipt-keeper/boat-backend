from app.core.domain.exceptions import ErrorDetail, NotFoundError, ValidationError
from app.modules.users.application.commands.register_push_token.command import (
    RegisterPushTokenCommand,
)
from app.modules.users.application.commands.register_push_token.result import (
    RegisterPushTokenResult,
)
from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.domain.model import UserPushToken


class RegisterPushTokenCommandUseCase:
    def __init__(self, *, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def execute(self, command: RegisterPushTokenCommand) -> RegisterPushTokenResult:
        _validate_push_token_command(command)
        state = await self._user_repository.find_account_state(user_id=command.user_id)
        if state is None:
            raise NotFoundError("사용자를 찾을 수 없습니다.")

        push_token = await self._user_repository.upsert_push_token(
            push_token=UserPushToken.create(
                user_id=command.user_id,
                device_id=command.device_id,
                fcm_token=command.fcm_token,
                platform=command.platform,
            )
        )
        return RegisterPushTokenResult(push_token_id=push_token.id)


def _validate_push_token_command(command: RegisterPushTokenCommand) -> None:
    details: list[ErrorDetail] = []
    if not command.device_id:
        details.append(
            ErrorDetail(field="deviceId", message="기기 식별자는 비어 있을 수 없습니다.")
        )
    if not command.fcm_token:
        details.append(ErrorDetail(field="fcmToken", message="FCM 토큰은 비어 있을 수 없습니다."))
    if details:
        raise ValidationError(details)

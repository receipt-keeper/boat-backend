from collections.abc import Callable
from datetime import UTC, datetime

from app.core.application.unit_of_work import UnitOfWork
from app.modules.notifications.application.commands.register_device_token.command import (
    RegisterDeviceTokenCommand,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)
from app.modules.notifications.domain.model import UserPushToken


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RegisterDeviceTokenCommandUseCase:
    def __init__(
        self,
        *,
        push_token_repository: PushTokenRepository,
        unit_of_work: UnitOfWork,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._push_token_repository = push_token_repository
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def execute(self, command: RegisterDeviceTokenCommand) -> UserPushToken:
        now = self._clock()
        UserPushToken.create(
            user_id=command.user_id,
            device_id=command.device_id,
            fcm_token=command.fcm_token,
            platform=command.platform,
            created_at=now,
            updated_at=now,
        )

        saved = await self._push_token_repository.register(
            user_id=command.user_id,
            device_id=command.device_id,
            fcm_token=command.fcm_token,
            platform=command.platform,
        )
        await self._unit_of_work.commit()
        return saved

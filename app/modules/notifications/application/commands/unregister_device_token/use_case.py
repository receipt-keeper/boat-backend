from app.core.application.unit_of_work import UnitOfWork
from app.modules.notifications.application.commands.unregister_device_token.command import (
    UnregisterDeviceTokenCommand,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)


class UnregisterDeviceTokenCommandUseCase:
    def __init__(
        self,
        *,
        push_token_repository: PushTokenRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._push_token_repository = push_token_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: UnregisterDeviceTokenCommand) -> None:
        await self._push_token_repository.unregister(
            user_id=command.user_id,
            fid=command.fid,
        )
        await self._unit_of_work.commit()

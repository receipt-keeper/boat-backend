from app.core.application.unit_of_work import UnitOfWork
from app.modules.notifications.application.commands.delete_user_push_tokens.command import (
    DeleteUserPushTokensCommand,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)


class DeleteUserPushTokensCommandUseCase:
    def __init__(
        self,
        *,
        push_token_repository: PushTokenRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._push_token_repository = push_token_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: DeleteUserPushTokensCommand) -> None:
        await self._push_token_repository.delete_by_user_id(user_id=command.user_id)
        await self._unit_of_work.commit()

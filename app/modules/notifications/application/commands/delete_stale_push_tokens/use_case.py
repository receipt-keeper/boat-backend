from app.core.application.unit_of_work import UnitOfWork
from app.modules.notifications.application.commands.delete_stale_push_tokens.command import (
    DeleteStalePushTokensCommand,
)
from app.modules.notifications.application.commands.delete_stale_push_tokens.result import (
    DeleteStalePushTokensResult,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)


class DeleteStalePushTokensCommandUseCase:
    def __init__(
        self,
        *,
        push_token_repository: PushTokenRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._push_token_repository = push_token_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: DeleteStalePushTokensCommand) -> DeleteStalePushTokensResult:
        deleted_count = await self._push_token_repository.delete_stale(
            older_than=command.older_than,
        )
        await self._unit_of_work.commit()
        return DeleteStalePushTokensResult(deleted_count=deleted_count)

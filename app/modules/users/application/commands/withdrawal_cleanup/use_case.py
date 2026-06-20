from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.ports.user_repository import UserRepository


class WithdrawalCleanupCommandUseCase:
    def __init__(self, *, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def execute(self, command: WithdrawalCleanupCommand) -> None:
        await self._user_repository.delete_account_state(user_id=command.user_id)

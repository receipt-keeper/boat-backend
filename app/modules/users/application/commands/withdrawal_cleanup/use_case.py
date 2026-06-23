from app.core.application.unit_of_work import UnitOfWork
from app.modules.users.application.commands.withdrawal_cleanup.command import (
    WithdrawalCleanupCommand,
)
from app.modules.users.application.ports.user_repository import UserRepository


class WithdrawalCleanupCommandUseCase:
    def __init__(self, *, user_repository: UserRepository, unit_of_work: UnitOfWork) -> None:
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: WithdrawalCleanupCommand) -> None:
        await self._user_repository.delete_account_state(user_id=command.user_id)
        await self._unit_of_work.commit()

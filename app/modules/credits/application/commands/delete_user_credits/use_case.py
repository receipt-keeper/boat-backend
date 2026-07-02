from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.delete_user_credits.command import (
    DeleteUserCreditsCommand,
)
from app.modules.credits.application.ports.credit_repository import CreditRepository


class DeleteUserCreditsCommandUseCase:
    def __init__(
        self,
        *,
        credit_repository: CreditRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._credit_repository = credit_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: DeleteUserCreditsCommand) -> None:
        await self._credit_repository.delete_by_user_id(user_id=command.user_id)
        await self._unit_of_work.commit()

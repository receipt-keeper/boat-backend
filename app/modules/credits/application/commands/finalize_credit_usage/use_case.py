from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionAppend,
)
from app.modules.credits.domain import CreditAction


class FinalizeCreditUsageCommandUseCase:
    def __init__(
        self,
        *,
        credit_repository: CreditRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._credit_repository = credit_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: UseCreditCommand) -> None:
        await self._credit_repository.append_transaction(
            transaction=CreditTransactionAppend(
                user_id=command.user_id,
                reason=command.reason,
                action=CreditAction.USE,
                amount=command.amount,
            )
        )
        await self._unit_of_work.commit()

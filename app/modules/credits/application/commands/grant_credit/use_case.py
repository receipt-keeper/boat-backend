from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.application.ports.credit_repository import CreditRepository
from app.modules.credits.domain import CreditAction


class GrantCreditCommandUseCase:
    def __init__(
        self,
        *,
        credit_repository: CreditRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._credit_repository = credit_repository
        self._unit_of_work = unit_of_work

    async def execute(self, command: GrantCreditCommand) -> None:
        user_credit = await self._credit_repository.get_user_credit_for_update(
            user_id=command.user_id,
        )
        user_credit.grant(command.amount)
        await self._credit_repository.save(user_credit=user_credit)
        await self._credit_repository.append_transaction(
            user_id=command.user_id,
            reason=command.reason,
            action=CreditAction.GRANT,
            amount=command.amount,
        )
        await self._unit_of_work.commit()

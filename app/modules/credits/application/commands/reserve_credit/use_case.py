from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.application.ports.credit_repository import CreditRepository


class ReserveCreditCommandUseCase:
    def __init__(self, *, credit_repository: CreditRepository) -> None:
        self._credit_repository = credit_repository

    async def execute(self, command: UseCreditCommand) -> None:
        user_credit = await self._credit_repository.get_user_credit_for_update(
            user_id=command.user_id,
        )
        user_credit.use(command.amount)
        await self._credit_repository.save(user_credit=user_credit)

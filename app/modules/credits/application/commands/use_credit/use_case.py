from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.finalize_credit_usage.use_case import (
    FinalizeCreditUsageCommandUseCase,
)
from app.modules.credits.application.commands.reserve_credit.use_case import (
    ReserveCreditCommandUseCase,
)
from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.application.ports.credit_repository import CreditRepository


class UseCreditCommandUseCase:
    def __init__(
        self,
        *,
        credit_repository: CreditRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._credit_repository = credit_repository
        self._unit_of_work = unit_of_work
        self._reserve_credit_use_case = ReserveCreditCommandUseCase(
            credit_repository=credit_repository
        )
        self._finalize_credit_usage_use_case = FinalizeCreditUsageCommandUseCase(
            credit_repository=credit_repository,
            unit_of_work=unit_of_work,
        )

    async def execute(self, command: UseCreditCommand) -> None:
        await self._reserve_credit_use_case.execute(command)
        await self._finalize_credit_usage_use_case.execute(command)

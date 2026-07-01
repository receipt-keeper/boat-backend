from app.modules.credits.application.ports.credit_repository import CreditRepository
from app.modules.credits.application.queries.get_credit_balance.query import (
    GetCreditBalanceQuery,
)
from app.modules.credits.domain import CreditBalance


class GetCreditBalanceQueryUseCase:
    def __init__(self, *, credit_repository: CreditRepository) -> None:
        self._credit_repository = credit_repository

    async def execute(self, query: GetCreditBalanceQuery) -> CreditBalance:
        return await self._credit_repository.get_balance(user_id=query.user_id)

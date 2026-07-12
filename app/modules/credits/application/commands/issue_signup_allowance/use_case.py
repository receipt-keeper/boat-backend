from typing import Final

from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.application.commands.grant_credit.use_case import (
    GrantCreditCommandUseCase,
)
from app.modules.credits.application.commands.issue_signup_allowance.command import (
    IssueSignupAllowanceCommand,
    signup_allowance_idempotency_key,
)
from app.modules.credits.application.commands.issue_signup_allowance.result import (
    IssueSignupAllowanceCommandResult,
    SignupAllowanceOutcome,
)
from app.modules.credits.application.ports.credit_repository import CreditRepository
from app.modules.credits.domain import CreditAmount, CreditReason

# 가입 보너스 수량은 이 use case가 소유한다 (auth 어댑터는 더 이상 이 상수를 갖지 않는다).
INITIAL_SIGNUP_ALLOWANCE_COUNT: Final = 5


class IssueSignupAllowanceCommandUseCase:
    """가입 보너스를 claim-first로 지급한다.

    전 버전 handle(candidate_handles)로 기존 claim을 먼저 조회해, 있으면 재지급 없이
    purge_after만 NULL로 되돌려 재활성화한다(보존 기간 내 재가입). 없으면 현행 handle
    로 idempotency_key를 채워 기존 GrantCreditCommandUseCase 경로로 최초 지급한다 -
    동시 중복 지급은 그 경로의 idempotency 흡수(unique index + rollback replay)가
    그대로 처리한다.
    """

    def __init__(
        self,
        *,
        credit_repository: CreditRepository,
        grant_credit_command_use_case: GrantCreditCommandUseCase,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._credit_repository = credit_repository
        self._grant_credit_command_use_case = grant_credit_command_use_case
        self._unit_of_work = unit_of_work

    async def execute(
        self,
        command: IssueSignupAllowanceCommand,
    ) -> IssueSignupAllowanceCommandResult:
        candidate_keys = [
            signup_allowance_idempotency_key(handle) for handle in command.candidate_handles
        ]
        existing_claim = await self._credit_repository.find_transaction_by_idempotency_keys(
            idempotency_keys=candidate_keys,
        )
        if existing_claim is not None:
            await self._credit_repository.set_transaction_purge_after(
                transaction_id=existing_claim.transaction_id,
                purge_after=None,
            )
            await self._unit_of_work.commit()
            balance = await self._credit_repository.get_balance(user_id=command.user_id)
            return IssueSignupAllowanceCommandResult(
                outcome=SignupAllowanceOutcome.REACTIVATED,
                total_granted_count=balance.total_granted_count,
                remaining_count=balance.remaining_count,
            )

        grant_result = await self._grant_credit_command_use_case.execute(
            GrantCreditCommand(
                user_id=command.user_id,
                amount=CreditAmount(value=INITIAL_SIGNUP_ALLOWANCE_COUNT),
                reason=CreditReason.MONTHLY_OCR_ALLOWANCE,
                idempotency_key=signup_allowance_idempotency_key(command.subject_handle),
            )
        )
        return IssueSignupAllowanceCommandResult(
            outcome=SignupAllowanceOutcome.ISSUED,
            total_granted_count=grant_result.total_granted_count,
            remaining_count=grant_result.remaining_count,
        )

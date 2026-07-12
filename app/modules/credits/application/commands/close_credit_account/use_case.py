from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.close_credit_account.command import (
    CloseCreditsAccountCommand,
)
from app.modules.credits.application.commands.issue_signup_allowance.command import (
    signup_allowance_idempotency_key,
)
from app.modules.credits.application.ports.credit_repository import CreditRepository
from app.modules.credits.domain.events import UserCreditsDeleted


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CloseCreditsAccountCommandUseCase:
    """계정 탈퇴 시 크레딧 상태를 정리하되, 가입 보너스 claim은 보존 기간 동안 남긴다.

    user_credits(잔액)와 signup-allowance claim을 제외한 나머지 transactions는 즉시
    삭제한다. signup-allowance claim은 삭제하지 않고 purge_after만
    `now + credit_claim_retention_days`로 채워 파기 폴러(CreditClaimPurger)에 위임한다
    - 보존 기간 내 재가입 시 재지급 없이 재활성화하기 위한 신호로 쓰인다.
    candidate_handles가 비어 있으면(신원 조회 불가 엣지) 보존 없이 전량 삭제한다.
    """

    def __init__(
        self,
        *,
        credit_repository: CreditRepository,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
        retention_days: int,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._credit_repository = credit_repository
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher
        self._retention_days = retention_days
        self._clock = clock

    async def execute(self, command: CloseCreditsAccountCommand) -> None:
        if not command.candidate_handles:
            await self._credit_repository.delete_by_user_id(user_id=command.user_id)
            await self._event_publisher.publish([UserCreditsDeleted(user_id=command.user_id)])
            await self._unit_of_work.commit()
            return

        candidate_keys = [
            signup_allowance_idempotency_key(handle) for handle in command.candidate_handles
        ]
        existing_claim = await self._credit_repository.find_transaction_by_idempotency_keys(
            idempotency_keys=candidate_keys,
        )
        preserved_transaction_ids = (
            [existing_claim.transaction_id] if existing_claim is not None else []
        )
        await self._credit_repository.delete_user_credit_state_except_transactions(
            user_id=command.user_id,
            preserved_transaction_ids=preserved_transaction_ids,
        )
        if existing_claim is not None:
            await self._credit_repository.set_transaction_purge_after(
                transaction_id=existing_claim.transaction_id,
                purge_after=self._clock() + timedelta(days=self._retention_days),
            )

        await self._event_publisher.publish([UserCreditsDeleted(user_id=command.user_id)])
        await self._unit_of_work.commit()

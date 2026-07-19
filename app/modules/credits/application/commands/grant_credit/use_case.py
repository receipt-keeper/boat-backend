from app.core.application.event_publisher import EventPublisher
from app.core.application.unit_of_work import UnitOfWork
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.application.commands.grant_credit.result import (
    GrantCreditCommandResult,
)
from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionAppend,
    CreditTransactionSourceKey,
    CreditTransactionWriteConflictError,
)
from app.modules.credits.domain import CreditAction
from app.modules.credits.domain.exceptions import CreditBalancePreconditionError


class GrantCreditCommandUseCase:
    def __init__(
        self,
        *,
        credit_repository: CreditRepository,
        unit_of_work: UnitOfWork,
        event_publisher: EventPublisher,
    ) -> None:
        self._credit_repository = credit_repository
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher

    async def execute(self, command: GrantCreditCommand) -> GrantCreditCommandResult:
        if await self._is_duplicate_grant(command):
            balance = await self._credit_repository.get_balance(user_id=command.user_id)
            return GrantCreditCommandResult(
                total_granted_count=balance.total_granted_count,
                remaining_count=balance.remaining_count,
            )
        user_credit = await self._credit_repository.get_user_credit_for_update(
            user_id=command.user_id,
        )
        _ensure_required_remaining_count(
            command=command,
            remaining_count=user_credit.remaining_count,
        )
        user_credit.grant(
            command.amount,
            reason=command.reason,
            source_type=command.source_type,
            source_id=command.source_id,
            idempotency_key=command.idempotency_key,
        )
        await self._credit_repository.save(user_credit=user_credit)
        await self._credit_repository.append_transaction(
            transaction=CreditTransactionAppend(
                user_id=command.user_id,
                reason=command.reason,
                action=CreditAction.GRANT,
                amount=command.amount,
                source_type=command.source_type,
                source_id=command.source_id,
                idempotency_key=command.idempotency_key,
            )
        )
        # 발행은 flush/commit 이전에 수행한다 - 같은 세션에 insert된 outbox row가
        # 아래 CreditTransactionWriteConflictError 분기의 rollback()과 함께
        # 원자적으로 소거되도록 하기 위함이다(멱등 replay에서 유령 이벤트 방지).
        events = user_credit.pull_events()
        await self._event_publisher.publish(events)
        try:
            await self._credit_repository.flush_pending_writes()
            await self._unit_of_work.commit()
        except CreditTransactionWriteConflictError:
            if not _has_idempotent_identity(command):
                raise
            await self._unit_of_work.rollback()
            balance = await self._credit_repository.get_balance(user_id=command.user_id)
            _ensure_required_remaining_count(
                command=command,
                remaining_count=balance.remaining_count,
            )
            return GrantCreditCommandResult(
                total_granted_count=balance.total_granted_count,
                remaining_count=balance.remaining_count,
            )
        return GrantCreditCommandResult(
            total_granted_count=user_credit.total_granted_count,
            remaining_count=user_credit.remaining_count,
        )

    async def _is_duplicate_grant(self, command: GrantCreditCommand) -> bool:
        if command.idempotency_key is not None and (
            await self._credit_repository.exists_transaction_with_idempotency_key(
                idempotency_key=command.idempotency_key,
            )
        ):
            return True
        if command.source_type is None or command.source_id is None:
            return False
        return await self._credit_repository.exists_transaction_with_source(
            source=CreditTransactionSourceKey(
                user_id=command.user_id,
                source_type=command.source_type,
                source_id=command.source_id,
                action=CreditAction.GRANT,
            )
        )


def _has_idempotent_identity(command: GrantCreditCommand) -> bool:
    return command.idempotency_key is not None or (
        command.source_type is not None and command.source_id is not None
    )


def _ensure_required_remaining_count(
    *,
    command: GrantCreditCommand,
    remaining_count: int,
) -> None:
    required = command.required_remaining_count
    if required is not None and remaining_count != required:
        raise CreditBalancePreconditionError()

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from app.modules.credits.application.ports.credit_repository import (
    CreditRepository,
    CreditTransactionAppend,
    CreditTransactionCursor,
    CreditTransactionHandle,
    CreditTransactionListResult,
    CreditTransactionSourceKey,
)
from app.modules.credits.application.queries.get_credit_balance.use_case import (
    GetCreditBalanceQueryUseCase,
)
from app.modules.credits.domain import (
    CreditBalance,
    UserCredit,
)
from app.modules.usage.application.queries.get_usage_snapshot.query import (
    GetUsageSnapshotQuery,
)
from app.modules.usage.application.queries.get_usage_snapshot.use_case import (
    GetUsageSnapshotQueryUseCase,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000101")


class CreditRepositoryStub(CreditRepository):
    def __init__(self, balance: CreditBalance) -> None:
        self._balance = balance

    async def get_balance(self, *, user_id: UUID) -> CreditBalance:
        return self._balance

    async def get_user_credit_for_update(self, *, user_id: UUID) -> UserCredit:
        raise AssertionError("usage snapshot should not lock credit balance")

    async def save(self, *, user_credit: UserCredit) -> None:
        raise AssertionError("usage snapshot should not save credit balance")

    async def append_transaction(
        self,
        *,
        transaction: CreditTransactionAppend,
    ) -> None:
        raise AssertionError("usage snapshot should not append credit transactions")

    async def flush_pending_writes(self) -> None:
        raise AssertionError("usage snapshot should not flush credit writes")

    async def exists_transaction_with_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> bool:
        raise AssertionError("usage snapshot should not check credit idempotency")

    async def exists_transaction_with_source(
        self,
        *,
        source: CreditTransactionSourceKey,
    ) -> bool:
        raise AssertionError("usage snapshot should not check credit source")

    async def delete_by_user_id(self, *, user_id: UUID) -> None:
        raise AssertionError("usage snapshot should not delete credit state")

    async def find_transaction_by_idempotency_keys(
        self,
        *,
        idempotency_keys: Sequence[str],
    ) -> CreditTransactionHandle | None:
        raise AssertionError("usage snapshot should not look up credit claims")

    async def set_transaction_purge_after(
        self,
        *,
        transaction_id: UUID,
        purge_after: datetime | None,
    ) -> None:
        raise AssertionError("usage snapshot should not mutate credit claim purge state")

    async def delete_user_credit_state_except_transactions(
        self,
        *,
        user_id: UUID,
        preserved_transaction_ids: Sequence[UUID],
    ) -> None:
        raise AssertionError("usage snapshot should not delete credit state")

    async def list_transactions(
        self,
        *,
        user_id: UUID,
        cursor: CreditTransactionCursor | None,
        limit: int,
    ) -> CreditTransactionListResult:
        raise AssertionError("usage snapshot should not list credit transactions")


async def test_usage_snapshot_allows_ocr_when_credit_remains() -> None:
    # Given: 크레딧 잔여 횟수가 1회인 사용자 조회 use case가 있다.
    use_case = _usage_snapshot_use_case(
        CreditBalance(total_granted_count=5, used_count=4, remaining_count=1)
    )

    # When: usage snapshot을 조회한다.
    snapshot = await use_case.execute(GetUsageSnapshotQuery(user_id=USER_ID))

    # Then: OCR 사용 가능 여부는 잔여 횟수에서 true로 파생된다.
    ocr_usage = snapshot.ocr
    assert ocr_usage.remaining_count == 1
    assert ocr_usage.can_analyze is True


async def test_usage_snapshot_blocks_ocr_when_credit_is_empty() -> None:
    # Given: 크레딧 잔여 횟수가 0회인 사용자 조회 use case가 있다.
    use_case = _usage_snapshot_use_case(
        CreditBalance(total_granted_count=5, used_count=5, remaining_count=0)
    )

    # When: usage snapshot을 조회한다.
    snapshot = await use_case.execute(GetUsageSnapshotQuery(user_id=USER_ID))

    # Then: OCR 사용 가능 여부는 잔여 횟수에서 false로 파생된다.
    ocr_usage = snapshot.ocr
    assert ocr_usage.remaining_count == 0
    assert ocr_usage.can_analyze is False


def _usage_snapshot_use_case(balance: CreditBalance) -> GetUsageSnapshotQueryUseCase:
    return GetUsageSnapshotQueryUseCase(
        credit_balance_query_use_case=GetCreditBalanceQueryUseCase(
            credit_repository=CreditRepositoryStub(balance)
        )
    )

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import CheckConstraint, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.domain.exceptions import ValidationError
from app.modules.credits.application.queries.list_credit_transactions.query import (
    ListCreditTransactionsQuery,
)
from app.modules.credits.application.queries.list_credit_transactions.use_case import (
    InvalidCreditTransactionCursorError,
    ListCreditTransactionsQueryUseCase,
)
from app.modules.credits.domain import (
    CreditAction,
    CreditReason,
)
from app.modules.credits.infrastructure.persistence import orm
from app.modules.credits.infrastructure.persistence.repository import (
    SqlAlchemyCreditRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000101")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000102")
EXPECTED_REASON_CONSTRAINTS = {
    "ck_credit_transactions_feature_key_allowed": "feature_key IN ('ocr')",
    "ck_credit_transactions_reason_allowed": (
        "reason IN ('monthlyOcrAllowance', 'eventOcrAllowance', 'ocrUsage')"
    ),
    "ck_credit_transactions_action_allowed": "action IN ('grant', 'use')",
    "ck_credit_transactions_amount_positive": "amount > 0",
}


def test_credit_orm_uses_user_credit_snapshot_table() -> None:
    credit_metadata = orm.CreditTransaction.metadata

    assert "user_credits" in credit_metadata.tables
    assert "credit_accounts" not in credit_metadata.tables
    assert hasattr(orm, "UserCredit")
    assert not hasattr(orm, "Credit" + "Account")

    user_credits = credit_metadata.tables["user_credits"]
    assert list(user_credits.primary_key.columns.keys()) == ["user_id", "feature_key"]
    assert set(user_credits.c.keys()) == {
        "user_id",
        "feature_key",
        "total_granted_count",
        "used_count",
        "remaining_count",
        "created_at",
        "updated_at",
    }


def test_credit_transaction_orm_declares_allowed_value_constraints() -> None:
    credit_transactions = orm.CreditTransaction.metadata.tables["credit_transactions"]
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in credit_transactions.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert constraints == EXPECTED_REASON_CONSTRAINTS
    assert "feature_key" in credit_transactions.c


async def test_credit_repository_returns_zero_snapshot_when_account_missing(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 크레딧 계정이 없는 사용자 ID가 있다.
    async with postgres_session_factory() as session:
        repository = SqlAlchemyCreditRepository(session)

        # When: 사용자 크레딧 snapshot을 조회한다.
        balance = await repository.get_balance(user_id=USER_ID)

    # Then: 계정 미생성 사용자는 0/0/0 snapshot으로 해석된다.
    assert balance.total_granted_count == 0
    assert balance.used_count == 0
    assert balance.remaining_count == 0


async def test_credit_repository_rejects_inconsistent_account_counts(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: DB check를 우회한 legacy/corrupt snapshot 값이 있다.
    async with postgres_session_factory() as session:
        await session.execute(
            text("ALTER TABLE user_credits DROP CONSTRAINT ck_user_credits_counts_consistent")
        )
        session.add(
            _user_credit_orm_type()(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=12,
                used_count=5,
                remaining_count=6,
            )
        )
        await session.commit()

    async with postgres_session_factory() as session:
        repository = SqlAlchemyCreditRepository(session)

        # When/Then: production read path가 aggregate restore를 거쳐 값을 거절한다.
        with pytest.raises(ValidationError) as exc_info:
            await repository.get_balance(user_id=USER_ID)

    assert [detail.field for detail in exc_info.value.details] == ["total_granted_count"]


async def test_credit_transaction_query_pages_by_created_at_and_id_cursor(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 같은 시각 tie-breaker를 포함한 크레딧 ledger가 저장되어 있다.
    async with postgres_session_factory() as session:
        session.add(
            _user_credit_orm_type()(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=12,
                used_count=5,
                remaining_count=7,
            )
        )
        session.add_all(
            [
                _transaction(
                    transaction_id=UUID("00000000-0000-0000-0000-000000000001"),
                    user_id=USER_ID,
                    reason=CreditReason("monthlyOcrAllowance"),
                    action=CreditAction.GRANT,
                    amount=10,
                    created_at=datetime(2026, 6, 29, 9, 0, tzinfo=UTC),
                ),
                _transaction(
                    transaction_id=UUID("00000000-0000-0000-0000-000000000002"),
                    user_id=USER_ID,
                    reason=CreditReason("ocrUsage"),
                    action=CreditAction.USE,
                    amount=3,
                    created_at=datetime(2026, 6, 29, 9, 0, tzinfo=UTC),
                ),
                _transaction(
                    transaction_id=UUID("00000000-0000-0000-0000-000000000003"),
                    user_id=USER_ID,
                    reason=CreditReason("ocrUsage"),
                    action=CreditAction.USE,
                    amount=2,
                    created_at=datetime(2026, 6, 29, 9, 5, tzinfo=UTC),
                ),
                _transaction(
                    transaction_id=UUID("00000000-0000-0000-0000-000000000004"),
                    user_id=OTHER_USER_ID,
                    reason=CreditReason("eventOcrAllowance"),
                    action=CreditAction.GRANT,
                    amount=99,
                    created_at=datetime(2026, 6, 29, 8, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

    async with postgres_session_factory() as session:
        use_case = ListCreditTransactionsQueryUseCase(
            credit_repository=SqlAlchemyCreditRepository(session)
        )

        # When: 첫 page와 cursor 이후 page를 순서대로 조회한다.
        first_page = await use_case.execute(ListCreditTransactionsQuery(user_id=USER_ID, limit=2))
        next_page = await use_case.execute(
            ListCreditTransactionsQuery(
                user_id=USER_ID,
                cursor=first_page.next_cursor,
                limit=2,
            )
        )

    # Then: 목록은 user_id로 격리되고 created_at/id 오름차순 cursor로 이어진다.
    assert [transaction.transaction_id for transaction in first_page.transactions] == [
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
    ]
    assert first_page.has_next is True
    assert first_page.next_cursor is not None
    assert first_page.total_count == 3
    assert [transaction.transaction_id for transaction in next_page.transactions] == [
        UUID("00000000-0000-0000-0000-000000000003"),
    ]
    assert next_page.has_next is False
    assert next_page.next_cursor is None
    assert next_page.total_count == 3


async def test_credit_transaction_query_rejects_invalid_cursor(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Given: 크레딧 내역 query use case가 있다.
    async with postgres_session_factory() as session:
        use_case = ListCreditTransactionsQueryUseCase(
            credit_repository=SqlAlchemyCreditRepository(session)
        )

        # When/Then: 형식이 맞지 않는 cursor는 도메인 에러로 거절된다.
        with pytest.raises(InvalidCreditTransactionCursorError) as exc_info:
            await use_case.execute(
                ListCreditTransactionsQuery(user_id=USER_ID, cursor="not-a-cursor")
            )

    assert exc_info.value.message == "크레딧 내역 cursor가 올바르지 않습니다."


def _transaction(
    *,
    transaction_id: UUID,
    user_id: UUID,
    reason: CreditReason,
    action: CreditAction,
    amount: int,
    created_at: datetime,
) -> orm.CreditTransaction:
    return orm.CreditTransaction(
        id=transaction_id,
        user_id=user_id,
        feature_key="ocr",
        reason=reason.value,
        action=action.value,
        amount=amount,
        created_at=created_at,
    )


def _user_credit_orm_type() -> type[orm.UserCredit]:
    return orm.UserCredit

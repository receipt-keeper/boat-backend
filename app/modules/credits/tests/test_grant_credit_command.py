from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import ValidationError
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.application.commands.grant_credit.use_case import (
    GrantCreditCommandUseCase,
)
from app.modules.credits.domain import CreditAction, CreditAmount, CreditReason
from app.modules.credits.infrastructure.persistence import orm
from app.modules.credits.infrastructure.persistence.repository import (
    SqlAlchemyCreditRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000101")
SOURCE_ID = UUID("00000000-0000-0000-0000-000000000901")

if TYPE_CHECKING:
    from app.modules.credits.domain import CreditSourceType


async def test_grant_credit_command_creates_snapshot_and_appends_ledger(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        use_case = GrantCreditCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
        )

        await use_case.execute(
            GrantCreditCommand(
                user_id=USER_ID,
                amount=CreditAmount(value=5, field_name="amount"),
                reason=CreditReason.MONTHLY_OCR_ALLOWANCE,
            )
        )

    async with postgres_session_factory() as session:
        saved_credit = await session.get(
            orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
            )
        )

    assert saved_credit is not None
    assert saved_credit.total_granted_count == 5
    assert saved_credit.used_count == 0
    assert saved_credit.remaining_count == 5
    assert len(saved_transactions) == 1
    assert saved_transactions[0].reason == CreditReason.MONTHLY_OCR_ALLOWANCE.value
    assert saved_transactions[0].action == CreditAction.GRANT.value
    assert saved_transactions[0].amount == 5
    assert saved_transactions[0].source_type is None
    assert saved_transactions[0].source_id is None
    assert saved_transactions[0].idempotency_key is None


async def test_grant_credit_command_records_source_metadata(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source_type = _promotion_redemption_source_type()
    async with postgres_session_factory() as session:
        use_case = GrantCreditCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
        )

        await use_case.execute(
            GrantCreditCommand(
                user_id=USER_ID,
                amount=CreditAmount(value=5, field_name="amount"),
                reason=CreditReason.EVENT_OCR_ALLOWANCE,
                source_type=source_type,
                source_id=SOURCE_ID,
                idempotency_key=f"promotionRedemption:{SOURCE_ID}:{USER_ID}",
            )
        )

    async with postgres_session_factory() as session:
        saved_credit = await session.get(
            orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        saved_transaction = await session.scalar(
            select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
        )

    assert saved_credit is not None
    assert saved_credit.total_granted_count == 5
    assert saved_credit.remaining_count == 5
    assert saved_transaction is not None
    assert saved_transaction.reason == CreditReason.EVENT_OCR_ALLOWANCE.value
    assert saved_transaction.source_type == source_type.value
    assert saved_transaction.source_id == SOURCE_ID
    assert saved_transaction.idempotency_key == f"promotionRedemption:{SOURCE_ID}:{USER_ID}"


def test_grant_credit_command_rejects_partial_source_metadata() -> None:
    source_type = _promotion_redemption_source_type()

    with pytest.raises(ValidationError) as source_type_only:
        GrantCreditCommand(
            user_id=USER_ID,
            amount=CreditAmount(value=5, field_name="amount"),
            reason=CreditReason.EVENT_OCR_ALLOWANCE,
            source_type=source_type,
        )

    with pytest.raises(ValidationError) as source_id_only:
        GrantCreditCommand(
            user_id=USER_ID,
            amount=CreditAmount(value=5, field_name="amount"),
            reason=CreditReason.EVENT_OCR_ALLOWANCE,
            source_id=SOURCE_ID,
        )

    assert [(detail.field, detail.message) for detail in source_type_only.value.details] == [
        ("source", "크레딧 출처 유형과 출처 ID는 함께 전달해야 합니다.")
    ]
    assert [(detail.field, detail.message) for detail in source_id_only.value.details] == [
        ("source", "크레딧 출처 유형과 출처 ID는 함께 전달해야 합니다.")
    ]


async def test_grant_credit_command_ignores_duplicate_idempotency_key_without_increment(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source_type = _promotion_redemption_source_type()
    idempotency_key = f"promotionRedemption:{SOURCE_ID}:{USER_ID}"
    command = GrantCreditCommand(
        user_id=USER_ID,
        amount=CreditAmount(value=5, field_name="amount"),
        reason=CreditReason.EVENT_OCR_ALLOWANCE,
        source_type=source_type,
        source_id=SOURCE_ID,
        idempotency_key=idempotency_key,
    )
    async with postgres_session_factory() as session:
        use_case = GrantCreditCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
        )

        await use_case.execute(command)
        await use_case.execute(command)

    async with postgres_session_factory() as session:
        saved_credit = await session.get(
            orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
            )
        )

    assert saved_credit is not None
    assert saved_credit.total_granted_count == 5
    assert saved_credit.remaining_count == 5
    assert len(saved_transactions) == 1
    assert saved_transactions[0].idempotency_key == idempotency_key


async def test_credit_transaction_source_guard_rejects_duplicate_source_tuple(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source_type = _promotion_redemption_source_type()
    async with postgres_session_factory() as session:
        session.add_all(
            [
                orm.CreditTransaction(
                    user_id=USER_ID,
                    feature_key="ocr",
                    reason=CreditReason.EVENT_OCR_ALLOWANCE.value,
                    action=CreditAction.GRANT.value,
                    amount=5,
                    source_type=source_type.value,
                    source_id=SOURCE_ID,
                ),
                orm.CreditTransaction(
                    user_id=USER_ID,
                    feature_key="ocr",
                    reason=CreditReason.EVENT_OCR_ALLOWANCE.value,
                    action=CreditAction.GRANT.value,
                    amount=5,
                    source_type=source_type.value,
                    source_id=SOURCE_ID,
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            await session.commit()


def _promotion_redemption_source_type() -> "CreditSourceType":
    from app.modules.credits.domain import CreditSourceType

    return CreditSourceType.PROMOTION_REDEMPTION

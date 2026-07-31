import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import ValidationError
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.application.commands.grant_credit.use_case import (
    GrantCreditCommandUseCase,
)
from app.modules.credits.dependencies import build_credits_event_registry
from app.modules.credits.domain import CreditAction, CreditAmount, CreditReason, UserCredit
from app.modules.credits.domain.exceptions import CreditBalancePreconditionError
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
            event_publisher=OutboxEventPublisher(
                session=session,
                registry=build_credits_event_registry(),
            ),
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
        saved_outbox_events = tuple(await session.scalars(select(OutboxEvent)))

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
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "CreditGranted"
    assert saved_outbox_events[0].payload["user_id"] == str(USER_ID)
    assert saved_outbox_events[0].payload["amount"] == 5


async def test_grant_credit_command_revalidates_required_balance_after_concurrent_commit(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        session.add(
            orm.UserCredit(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=0,
                used_count=0,
                remaining_count=0,
            )
        )
        await session.commit()

    lock_requested = asyncio.Event()
    async with (
        postgres_session_factory() as concurrent_grant_session,
        postgres_session_factory() as conditional_grant_session,
    ):
        locked_credit = await concurrent_grant_session.scalar(
            select(orm.UserCredit)
            .where(
                orm.UserCredit.user_id == USER_ID,
                orm.UserCredit.feature_key == "ocr",
            )
            .with_for_update()
        )
        assert locked_credit is not None
        locked_credit.total_granted_count = 5
        locked_credit.remaining_count = 5

        conditional_grant = asyncio.create_task(
            GrantCreditCommandUseCase(
                credit_repository=_LockProbeCreditRepository(
                    conditional_grant_session,
                    lock_requested=lock_requested,
                ),
                unit_of_work=SqlAlchemyUnitOfWork(conditional_grant_session),
                event_publisher=OutboxEventPublisher(
                    session=conditional_grant_session,
                    registry=build_credits_event_registry(),
                ),
            ).execute(
                GrantCreditCommand(
                    user_id=USER_ID,
                    amount=CreditAmount(value=2),
                    reason=CreditReason.EVENT_OCR_ALLOWANCE,
                    required_remaining_count=0,
                )
            )
        )
        await lock_requested.wait()
        assert not conditional_grant.done()

        await concurrent_grant_session.commit()

        with pytest.raises(CreditBalancePreconditionError):
            await conditional_grant

    async with postgres_session_factory() as session:
        saved_credit = await session.get(
            orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        saved_transactions = tuple(await session.scalars(select(orm.CreditTransaction)))

    assert saved_credit is not None
    assert saved_credit.remaining_count == 5
    assert saved_transactions == ()


async def test_grant_credit_command_records_source_metadata(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    source_type = _promotion_redemption_source_type()
    async with postgres_session_factory() as session:
        use_case = GrantCreditCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
            event_publisher=OutboxEventPublisher(
                session=session,
                registry=build_credits_event_registry(),
            ),
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
            event_publisher=OutboxEventPublisher(
                session=session,
                registry=build_credits_event_registry(),
            ),
        )

        await use_case.execute(command)

    # 두 번째 호출은 별도 세션에서 수행한다 - 동일 세션 재사용 시 첫 호출의
    # `_is_duplicate_grant` 조회 결과가 세션 identity map에 캐시돼 replay 분기를
    # 우회할 위험이 있다(멱등 replay는 신규 요청 세션에서 일어나는 것이 현실적 시나리오).
    async with postgres_session_factory() as session:
        use_case = GrantCreditCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
            event_publisher=OutboxEventPublisher(
                session=session,
                registry=build_credits_event_registry(),
            ),
        )

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
        saved_outbox_events = tuple(await session.scalars(select(OutboxEvent)))

    assert saved_credit is not None
    assert saved_credit.total_granted_count == 5
    assert saved_credit.remaining_count == 5
    assert len(saved_transactions) == 1
    assert saved_transactions[0].idempotency_key == idempotency_key
    # 멱등 replay 분기(신규 상태 변경 없음)에서 outbox 신규 row가 발생하지 않는다.
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "CreditGranted"


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


class _LockProbeCreditRepository(SqlAlchemyCreditRepository):
    def __init__(
        self,
        session: AsyncSession,
        *,
        lock_requested: asyncio.Event,
    ) -> None:
        super().__init__(session)
        self._lock_requested = lock_requested

    async def get_user_credit_for_update(self, *, user_id: UUID) -> UserCredit:
        self._lock_requested.set()
        return await super().get_user_credit_for_update(user_id=user_id)


def _promotion_redemption_source_type() -> "CreditSourceType":
    from app.modules.credits.domain import CreditSourceType

    return CreditSourceType.PROMOTION_REDEMPTION

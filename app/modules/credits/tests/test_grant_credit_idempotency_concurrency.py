from uuid import UUID

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.application.commands.grant_credit.result import (
    GrantCreditCommandResult,
)
from app.modules.credits.application.commands.grant_credit.use_case import (
    GrantCreditCommandUseCase,
)
from app.modules.credits.dependencies import build_credits_event_registry
from app.modules.credits.domain import CreditAmount, CreditReason, CreditSourceType
from app.modules.credits.infrastructure.persistence import orm
from app.modules.credits.infrastructure.persistence.repository import (
    SqlAlchemyCreditRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000601")
SOURCE_ID = UUID("00000000-0000-0000-0000-000000000602")
IDEMPOTENCY_KEY = f"promotionRedemption:{SOURCE_ID}:{USER_ID}"


async def test_concurrent_same_idempotency_key_retry_returns_stable_result_without_double_grant(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    command = GrantCreditCommand(
        user_id=USER_ID,
        amount=CreditAmount(value=5, field_name="amount"),
        reason=CreditReason.EVENT_OCR_ALLOWANCE,
        source_type=CreditSourceType.PROMOTION_REDEMPTION,
        source_id=SOURCE_ID,
        idempotency_key=IDEMPOTENCY_KEY,
    )
    start = anyio.Event()
    results: list[GrantCreditCommandResult] = []

    async def grant_once() -> None:
        await start.wait()
        async with postgres_session_factory() as session:
            use_case = GrantCreditCommandUseCase(
                credit_repository=SqlAlchemyCreditRepository(session),
                unit_of_work=SqlAlchemyUnitOfWork(session),
                event_publisher=OutboxEventPublisher(
                    session=session,
                    registry=build_credits_event_registry(),
                ),
            )
            results.append(await use_case.execute(command))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(grant_once)
        task_group.start_soon(grant_once)
        start.set()

    async with postgres_session_factory() as session:
        saved_credit = await session.get(
            orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction).where(
                    orm.CreditTransaction.user_id == USER_ID,
                )
            )
        )
        saved_outbox_events = tuple(await session.scalars(select(OutboxEvent)))

    assert [(result.total_granted_count, result.remaining_count) for result in results] == [
        (5, 5),
        (5, 5),
    ]
    assert saved_credit is not None
    assert saved_credit.total_granted_count == 5
    assert saved_credit.remaining_count == 5
    assert len(saved_transactions) == 1
    assert saved_transactions[0].idempotency_key == IDEMPOTENCY_KEY
    # 동시 충돌 replay 분기(CreditTransactionWriteConflictError -> rollback)는
    # 패자 트랜잭션의 outbox insert를 함께 소거한다 - 승자 1건만 남는다.
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "CreditGranted"

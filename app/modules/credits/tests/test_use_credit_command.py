from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.credits.application.commands.delete_user_credits.command import (
    DeleteUserCreditsCommand,
)
from app.modules.credits.application.commands.delete_user_credits.use_case import (
    DeleteUserCreditsCommandUseCase,
)
from app.modules.credits.application.commands.finalize_credit_usage.use_case import (
    FinalizeCreditUsageCommandUseCase,
)
from app.modules.credits.application.commands.reserve_credit.use_case import (
    ReserveCreditCommandUseCase,
)
from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.application.commands.use_credit.use_case import UseCreditCommandUseCase
from app.modules.credits.dependencies import build_credits_event_registry
from app.modules.credits.domain import (
    CreditAction,
    CreditAmount,
    CreditReason,
    InsufficientCreditError,
)
from app.modules.credits.infrastructure.persistence import orm
from app.modules.credits.infrastructure.persistence.repository import (
    SqlAlchemyCreditRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000101")


async def test_use_credit_command_decrements_balance_and_appends_ledger(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        session.add(
            orm.UserCredit(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=5,
                used_count=2,
                remaining_count=3,
            )
        )
        await session.commit()

    async with postgres_session_factory() as session:
        use_case = UseCreditCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
            event_publisher=OutboxEventPublisher(
                session=session,
                registry=build_credits_event_registry(),
            ),
        )

        await use_case.execute(
            UseCreditCommand(
                user_id=USER_ID,
                amount=CreditAmount(value=1, field_name="amount"),
                reason=CreditReason.OCR_USAGE,
            )
        )

    async with postgres_session_factory() as session:
        saved_credit = await session.get(
            orm.UserCredit,
            {"user_id": USER_ID, "feature_key": "ocr"},
        )
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction)
                .where(orm.CreditTransaction.user_id == USER_ID)
                .order_by(orm.CreditTransaction.created_at, orm.CreditTransaction.id)
            )
        )
        saved_outbox_events = tuple(await session.scalars(select(OutboxEvent)))

    assert saved_credit is not None
    assert saved_credit.total_granted_count == 5
    assert saved_credit.used_count == 3
    assert saved_credit.remaining_count == 2
    assert len(saved_transactions) == 1
    assert saved_transactions[0].reason == CreditReason.OCR_USAGE.value
    assert saved_transactions[0].action == CreditAction.USE.value
    assert saved_transactions[0].amount == 1
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "CreditUsed"


async def test_use_credit_command_rejects_insufficient_remaining_count(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        session.add(
            orm.UserCredit(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=5,
                used_count=5,
                remaining_count=0,
            )
        )
        await session.commit()

    async with postgres_session_factory() as session:
        use_case = UseCreditCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
            event_publisher=OutboxEventPublisher(
                session=session,
                registry=build_credits_event_registry(),
            ),
        )

        with pytest.raises(InsufficientCreditError):
            await use_case.execute(
                UseCreditCommand(
                    user_id=USER_ID,
                    amount=CreditAmount(value=1, field_name="amount"),
                    reason=CreditReason.OCR_USAGE,
                )
            )


async def test_reserved_credit_rolls_back_without_usage_ledger(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        session.add(
            orm.UserCredit(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=5,
                used_count=2,
                remaining_count=3,
            )
        )
        await session.commit()

    async with postgres_session_factory() as session:
        command = UseCreditCommand(
            user_id=USER_ID,
            amount=CreditAmount(value=1, field_name="amount"),
            reason=CreditReason.OCR_USAGE,
        )
        await ReserveCreditCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session)
        ).execute(command)
        await SqlAlchemyUnitOfWork(session).rollback()

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
    assert saved_credit.used_count == 2
    assert saved_credit.remaining_count == 3
    assert saved_transactions == ()
    # reserve 단계는 EventPublisher를 주입받지 않는다 - CreditUsed는 finalize에서만
    # 발행되므로 rollback 전에도 outbox row는 애초에 생기지 않는다.
    assert saved_outbox_events == ()


async def test_finalize_credit_usage_commits_reserved_credit_and_usage_ledger(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        session.add(
            orm.UserCredit(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=5,
                used_count=2,
                remaining_count=3,
            )
        )
        await session.commit()

    async with postgres_session_factory() as session:
        command = UseCreditCommand(
            user_id=USER_ID,
            amount=CreditAmount(value=1, field_name="amount"),
            reason=CreditReason.OCR_USAGE,
        )
        repository = SqlAlchemyCreditRepository(session)
        unit_of_work = SqlAlchemyUnitOfWork(session)
        await ReserveCreditCommandUseCase(credit_repository=repository).execute(command)
        await FinalizeCreditUsageCommandUseCase(
            credit_repository=repository,
            unit_of_work=unit_of_work,
            event_publisher=OutboxEventPublisher(
                session=session,
                registry=build_credits_event_registry(),
            ),
        ).execute(command)

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
    assert saved_credit.used_count == 3
    assert saved_credit.remaining_count == 2
    assert len(saved_transactions) == 1
    assert saved_transactions[0].reason == CreditReason.OCR_USAGE.value
    # finalize가 사용 확정의 유일한 커밋 지점이므로 CreditUsed는 정확히 1건 발행된다.
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "CreditUsed"


async def test_delete_user_credits_command_removes_snapshot_and_ledger(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        session.add(
            orm.UserCredit(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=5,
                used_count=1,
                remaining_count=4,
            )
        )
        session.add(
            orm.CreditTransaction(
                user_id=USER_ID,
                feature_key="ocr",
                reason=CreditReason.MONTHLY_OCR_ALLOWANCE.value,
                action=CreditAction.GRANT.value,
                amount=5,
            )
        )
        await session.commit()

    async with postgres_session_factory() as session:
        await DeleteUserCreditsCommandUseCase(
            credit_repository=SqlAlchemyCreditRepository(session),
            unit_of_work=SqlAlchemyUnitOfWork(session),
            event_publisher=OutboxEventPublisher(
                session=session,
                registry=build_credits_event_registry(),
            ),
        ).execute(DeleteUserCreditsCommand(user_id=USER_ID))

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

    assert saved_credit is None
    assert saved_transactions == ()
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "UserCreditsDeleted"

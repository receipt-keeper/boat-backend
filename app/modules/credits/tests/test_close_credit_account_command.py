from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.modules.credits.application.commands.close_credit_account.command import (
    CloseCreditsAccountCommand,
)
from app.modules.credits.application.commands.close_credit_account.use_case import (
    CloseCreditsAccountCommandUseCase,
)
from app.modules.credits.dependencies import build_credits_event_registry
from app.modules.credits.domain import CreditAction, CreditReason
from app.modules.credits.infrastructure.persistence import orm
from app.modules.credits.infrastructure.persistence.repository import (
    SqlAlchemyCreditRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000801")
CURRENT_HANDLE = "v2:" + "b" * 64
RETENTION_DAYS = 180


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _fixed_clock(*, at: datetime) -> Callable[[], datetime]:
    def clock() -> datetime:
        return at

    return clock


def _build_use_case(
    session: AsyncSession,
    *,
    clock: Callable[[], datetime] = _utc_now,
) -> CloseCreditsAccountCommandUseCase:
    return CloseCreditsAccountCommandUseCase(
        credit_repository=SqlAlchemyCreditRepository(session),
        unit_of_work=SqlAlchemyUnitOfWork(session),
        event_publisher=OutboxEventPublisher(
            session=session,
            registry=build_credits_event_registry(),
        ),
        retention_days=RETENTION_DAYS,
        clock=clock,
    )


async def _seed_signup_allowance_claim(session: AsyncSession) -> None:
    session.add(
        orm.UserCredit(
            user_id=USER_ID,
            feature_key="ocr",
            total_granted_count=5,
            used_count=2,
            remaining_count=3,
        )
    )
    session.add(
        orm.CreditTransaction(
            user_id=USER_ID,
            feature_key="ocr",
            reason=CreditReason.MONTHLY_OCR_ALLOWANCE.value,
            action=CreditAction.GRANT.value,
            amount=5,
            idempotency_key=f"signup-allowance:{CURRENT_HANDLE}",
        )
    )
    session.add(
        orm.CreditTransaction(
            user_id=USER_ID,
            feature_key="ocr",
            reason=CreditReason.OCR_USAGE.value,
            action=CreditAction.USE.value,
            amount=2,
        )
    )
    await session.commit()


async def test_close_account_preserves_claim_and_sets_purge_after(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_signup_allowance_claim(session)

    now = datetime.now(UTC)
    async with postgres_session_factory() as session:
        await _build_use_case(session, clock=_fixed_clock(at=now)).execute(
            CloseCreditsAccountCommand(
                user_id=USER_ID,
                candidate_handles=(CURRENT_HANDLE,),
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

    # 잔액 스냅샷은 삭제된다(재가입 시 재활성화되더라도 잔액은 0에서 시작).
    assert saved_credit is None
    # 사용 내역은 삭제되고, signup-allowance claim 1건만 남는다.
    assert len(saved_transactions) == 1
    remaining = saved_transactions[0]
    assert remaining.idempotency_key == f"signup-allowance:{CURRENT_HANDLE}"
    assert remaining.purge_after is not None
    expected_purge_after = now + timedelta(days=RETENTION_DAYS)
    assert abs((remaining.purge_after - expected_purge_after).total_seconds()) < 5
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "UserCreditsDeleted"


async def test_close_account_with_empty_candidate_handles_falls_back_to_full_delete(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        await _seed_signup_allowance_claim(session)

    async with postgres_session_factory() as session:
        await _build_use_case(session).execute(
            CloseCreditsAccountCommand(user_id=USER_ID, candidate_handles=())
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

    assert saved_credit is None
    assert saved_transactions == ()
    assert len(saved_outbox_events) == 1
    assert saved_outbox_events[0].event_type == "UserCreditsDeleted"


async def test_close_account_without_matching_claim_deletes_all_transactions(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        session.add(
            orm.UserCredit(
                user_id=USER_ID,
                feature_key="ocr",
                total_granted_count=5,
                used_count=0,
                remaining_count=5,
            )
        )
        session.add(
            orm.CreditTransaction(
                user_id=USER_ID,
                feature_key="ocr",
                reason=CreditReason.EVENT_OCR_ALLOWANCE.value,
                action=CreditAction.GRANT.value,
                amount=5,
            )
        )
        await session.commit()

    async with postgres_session_factory() as session:
        await _build_use_case(session).execute(
            CloseCreditsAccountCommand(
                user_id=USER_ID,
                candidate_handles=(CURRENT_HANDLE,),
            )
        )

    async with postgres_session_factory() as session:
        saved_transactions = tuple(
            await session.scalars(
                select(orm.CreditTransaction).where(orm.CreditTransaction.user_id == USER_ID)
            )
        )

    assert saved_transactions == ()

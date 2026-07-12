from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.credits.domain import CreditAction, CreditReason
from app.modules.credits.infrastructure.persistence import orm
from app.modules.credits.infrastructure.persistence.claim_purger import CreditClaimPurger

USER_ID = UUID("00000000-0000-0000-0000-000000000901")


def _fixed_clock(*, at: datetime) -> Callable[[], datetime]:
    def clock() -> datetime:
        return at

    return clock


def _transaction(
    *,
    idempotency_key: str,
    purge_after: datetime | None,
) -> orm.CreditTransaction:
    return orm.CreditTransaction(
        user_id=USER_ID,
        feature_key="ocr",
        reason=CreditReason.MONTHLY_OCR_ALLOWANCE.value,
        action=CreditAction.GRANT.value,
        amount=5,
        idempotency_key=idempotency_key,
        purge_after=purge_after,
    )


async def test_run_once_deletes_only_elapsed_claims_and_preserves_active_or_future_ones(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    elapsed_key = "signup-allowance:elapsed"
    active_key = "signup-allowance:active"
    future_key = "signup-allowance:future"

    async with postgres_session_factory() as session:
        session.add(_transaction(idempotency_key=elapsed_key, purge_after=now - timedelta(days=1)))
        session.add(_transaction(idempotency_key=active_key, purge_after=None))
        session.add(_transaction(idempotency_key=future_key, purge_after=now + timedelta(days=179)))
        await session.flush()

        purger = CreditClaimPurger(clock=_fixed_clock(at=now))

        deleted_count = await purger.run_once(session)

        assert deleted_count == 1
        remaining_keys = [
            key
            for key in await session.scalars(
                select(orm.CreditTransaction.idempotency_key).where(
                    orm.CreditTransaction.idempotency_key.in_([elapsed_key, active_key, future_key])
                )
            )
            if key is not None
        ]
        assert sorted(remaining_keys) == sorted([active_key, future_key])

        await session.execute(
            delete(orm.CreditTransaction).where(
                orm.CreditTransaction.idempotency_key.in_([active_key, future_key])
            )
        )
        await session.commit()


async def test_run_once_is_noop_when_no_claims_are_elapsed(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    active_key = "signup-allowance:still-active"

    async with postgres_session_factory() as session:
        session.add(_transaction(idempotency_key=active_key, purge_after=None))
        await session.flush()

        purger = CreditClaimPurger(clock=_fixed_clock(at=now))

        deleted_count = await purger.run_once(session)

        assert deleted_count == 0

        await session.execute(
            delete(orm.CreditTransaction).where(orm.CreditTransaction.idempotency_key == active_key)
        )
        await session.commit()

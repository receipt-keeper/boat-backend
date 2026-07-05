from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.credits.application.ports.credit_repository import (
    CreditTransactionWriteConflictError,
)
from app.modules.credits.infrastructure.persistence import orm
from app.modules.credits.infrastructure.persistence.repository import (
    SqlAlchemyCreditRepository,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000101")


async def test_credit_repository_maps_first_grant_snapshot_conflict(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        repository = SqlAlchemyCreditRepository(session)
        session.add_all(
            [
                _user_credit_snapshot(),
                _user_credit_snapshot(),
            ]
        )

        with pytest.raises(CreditTransactionWriteConflictError):
            await repository.flush_pending_writes()

        await session.rollback()


def _user_credit_snapshot() -> orm.UserCredit:
    return orm.UserCredit(
        user_id=USER_ID,
        feature_key="ocr",
        total_granted_count=1,
        used_count=0,
        remaining_count=1,
    )

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.infrastructure.persistence import orm
from app.modules.auth.infrastructure.persistence.withdrawn_identity_purger import (
    WithdrawnIdentityPurger,
)


def _fixed_clock(*, at: datetime) -> Callable[[], datetime]:
    def clock() -> datetime:
        return at

    return clock


async def test_run_once_deletes_only_expired_rows_and_preserves_valid_rows(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # `run_once`는 자체적으로 commit하므로(파기 폴러 계약), rollback 기반이
    # 아닌 커밋 결과를 직접 관찰하는 방식으로 검증한다.
    now = datetime.now(UTC)
    expired_hash = "1" * 64
    valid_hash = "2" * 64

    async with postgres_session_factory() as session:
        session.add(
            orm.WithdrawnIdentity(
                identity_hash=expired_hash,
                withdrawn_at=now - timedelta(days=200),
                expires_at=now - timedelta(days=20),
            )
        )
        session.add(
            orm.WithdrawnIdentity(
                identity_hash=valid_hash,
                withdrawn_at=now,
                expires_at=now + timedelta(days=180),
            )
        )
        await session.flush()

        purger = WithdrawnIdentityPurger(clock=_fixed_clock(at=now))

        # When: run_once을 실행한다.
        deleted_count = await purger.run_once(session)

        # Then: 만료 row만 파기되고 유효 row는 남는다.
        assert deleted_count == 1
        remaining_hashes = (
            await session.scalars(
                select(orm.WithdrawnIdentity.identity_hash).where(
                    orm.WithdrawnIdentity.identity_hash.in_([expired_hash, valid_hash])
                )
            )
        ).all()
        assert list(remaining_hashes) == [valid_hash]

        await session.execute(
            delete(orm.WithdrawnIdentity).where(orm.WithdrawnIdentity.identity_hash == valid_hash)
        )
        await session.commit()


async def test_run_once_is_noop_when_no_rows_are_expired(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    valid_hash = "3" * 64

    async with postgres_session_factory() as session:
        session.add(
            orm.WithdrawnIdentity(
                identity_hash=valid_hash,
                withdrawn_at=now,
                expires_at=now + timedelta(days=180),
            )
        )
        await session.flush()

        purger = WithdrawnIdentityPurger(clock=_fixed_clock(at=now))

        deleted_count = await purger.run_once(session)

        assert deleted_count == 0

        await session.execute(
            delete(orm.WithdrawnIdentity).where(orm.WithdrawnIdentity.identity_hash == valid_hash)
        )
        await session.commit()

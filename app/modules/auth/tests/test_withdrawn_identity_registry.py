from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.infrastructure.persistence.withdrawn_identity_repository import (
    SqlAlchemyWithdrawnIdentityRegistry,
)

RETENTION_DAYS = 180


def _past_clock(*, days_ago: int) -> Callable[[], datetime]:
    fixed_now = datetime.now(UTC) - timedelta(days=days_ago)

    def clock() -> datetime:
        return fixed_now

    return clock


async def test_mark_withdrawn_then_exists_is_true(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        transaction = await session.begin()
        try:
            registry = SqlAlchemyWithdrawnIdentityRegistry(session, retention_days=RETENTION_DAYS)
            identity_hash = "a" * 64

            await registry.mark_withdrawn(identity_hashes=[identity_hash])

            assert await registry.exists(identity_hash=identity_hash) is True
        finally:
            await transaction.rollback()


async def test_unregistered_identity_hash_does_not_exist(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        transaction = await session.begin()
        try:
            registry = SqlAlchemyWithdrawnIdentityRegistry(session, retention_days=RETENTION_DAYS)

            assert await registry.exists(identity_hash="b" * 64) is False
        finally:
            await transaction.rollback()


async def test_expired_tombstone_row_does_not_exist(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        transaction = await session.begin()
        try:
            identity_hash = "c" * 64
            # Given: 200일 전 시각을 now로 삼는 clock으로 180일 보존을 기록하면
            # expires_at은 실제 현재 시각보다 20일 과거가 된다.
            past_registry = SqlAlchemyWithdrawnIdentityRegistry(
                session,
                retention_days=RETENTION_DAYS,
                clock=_past_clock(days_ago=200),
            )
            await past_registry.mark_withdrawn(identity_hashes=[identity_hash])

            # When: 실제 현재 시각 기준 registry로 exists를 조회한다.
            current_registry = SqlAlchemyWithdrawnIdentityRegistry(
                session,
                retention_days=RETENTION_DAYS,
            )

            # Then: 만료된 tombstone은 존재하지 않는 것으로 판정된다.
            assert await current_registry.exists(identity_hash=identity_hash) is False
        finally:
            await transaction.rollback()


async def test_re_marking_withdrawn_identity_refreshes_expires_at(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        transaction = await session.begin()
        try:
            identity_hash = "d" * 64
            # Given: 이미 만료된 tombstone이 존재한다.
            past_registry = SqlAlchemyWithdrawnIdentityRegistry(
                session,
                retention_days=RETENTION_DAYS,
                clock=_past_clock(days_ago=200),
            )
            await past_registry.mark_withdrawn(identity_hashes=[identity_hash])

            current_registry = SqlAlchemyWithdrawnIdentityRegistry(
                session,
                retention_days=RETENTION_DAYS,
            )
            assert await current_registry.exists(identity_hash=identity_hash) is False

            # When: 같은 신원 해시로 재탈퇴(upsert)를 기록한다.
            await current_registry.mark_withdrawn(identity_hashes=[identity_hash])

            # Then: expires_at이 갱신되어 다시 유효한 tombstone으로 판정된다.
            assert await current_registry.exists(identity_hash=identity_hash) is True
        finally:
            await transaction.rollback()


async def test_mark_withdrawn_records_all_identity_hashes_in_one_call(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        transaction = await session.begin()
        try:
            registry = SqlAlchemyWithdrawnIdentityRegistry(session, retention_days=RETENTION_DAYS)
            identity_hashes = ["e" * 64, "f" * 64]

            await registry.mark_withdrawn(identity_hashes=identity_hashes)

            for identity_hash in identity_hashes:
                assert await registry.exists(identity_hash=identity_hash) is True
        finally:
            await transaction.rollback()

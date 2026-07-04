from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config.settings import get_settings
from app.modules.notifications.infrastructure.persistence import orm
from app.modules.notifications.jobs.cleanup_stale_tokens import run

STALE_USER_ID = UUID("00000000-0000-0000-0000-000000000401")
FRESH_USER_ID = UUID("00000000-0000-0000-0000-000000000402")


async def test_cleanup_job_deletes_only_tokens_past_stale_window(
    postgres_async_database_url: str,
    postgres_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 기본 보존 기간(60일)을 넘긴 토큰과 방금 갱신된 토큰이 있다.
    now = datetime.now(UTC)
    async with postgres_session_factory() as session, session.begin():
        session.add(
            orm.UserPushToken(
                user_id=STALE_USER_ID,
                fid="fid-stale",
                platform="android",
                updated_at=now - timedelta(days=61),
            )
        )
        session.add(
            orm.UserPushToken(
                user_id=FRESH_USER_ID,
                fid="fid-fresh",
                platform="ios",
                updated_at=now,
            )
        )
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()

    try:
        # When: 정리 잡을 실행한다.
        deleted_count = await run()
    finally:
        get_settings.cache_clear()

    # Then: 보존 기간을 넘긴 토큰만 삭제되고 삭제 건수가 보고된다.
    assert deleted_count == 1
    async with postgres_session_factory() as session:
        remaining = list(await session.scalars(select(orm.UserPushToken)))
    assert [row.fid for row in remaining] == ["fid-fresh"]


async def test_cleanup_job_is_idempotent_when_nothing_is_stale(
    postgres_async_database_url: str,
    postgres_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 정리 대상이 없는 DB가 있다.
    monkeypatch.setenv("DATABASE_URL", postgres_async_database_url)
    get_settings.cache_clear()

    try:
        # When: 정리 잡을 두 번 실행한다.
        first_deleted_count = await run()
        second_deleted_count = await run()
    finally:
        get_settings.cache_clear()

    # Then: 두 번 모두 예외 없이 0건 삭제를 보고한다.
    assert first_deleted_count == 0
    assert second_deleted_count == 0

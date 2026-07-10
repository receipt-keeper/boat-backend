import ast
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.base import Base
from app.core.db.session import build_engine, build_session_factory
from app.core.domain.exceptions import ValidationError
from app.modules.users.application.ports.user_repository import (
    ListUserNotificationCandidatesQuery,
    UserNotificationCandidateCursor,
)
from app.modules.users.infrastructure.persistence import orm
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository

PROJECT_ROOT = Path(__file__).resolve().parents[4]
USERS_ROOT = PROJECT_ROOT / "app" / "modules" / "users"
AS_OF = date(2026, 7, 9)


async def test_notification_candidates_page_by_created_at_and_id_cursor(
    user_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with user_session_factory() as session:
        await _seed_users(
            session,
            (
                (1, datetime(2026, 7, 2, 9, tzinfo=UTC)),
                (3, datetime(2026, 6, 25, 9, tzinfo=UTC)),
                (2, datetime(2026, 6, 25, 9, tzinfo=UTC)),
                (4, datetime(2026, 6, 18, 9, tzinfo=UTC)),
                (5, datetime(2026, 7, 3, 9, tzinfo=UTC)),
            ),
        )
        repository = SqlAlchemyUserRepository(session)

        first_page = await repository.list_notification_candidates(
            query=ListUserNotificationCandidatesQuery(as_of=AS_OF, batch_size=2)
        )
        second_page = await repository.list_notification_candidates(
            query=ListUserNotificationCandidatesQuery(
                as_of=AS_OF,
                batch_size=2,
                cursor=first_page.next_cursor,
            )
        )

    assert [candidate.user_id for candidate in first_page.candidates] == [
        UUID(int=4),
        UUID(int=2),
    ]
    assert first_page.next_cursor == UserNotificationCandidateCursor(
        created_at=datetime(2026, 6, 25, 9, tzinfo=UTC),
        user_id=UUID(int=2),
    )
    assert [candidate.user_id for candidate in second_page.candidates] == [
        UUID(int=3),
        UUID(int=1),
    ]
    assert [candidate.cursor_id for candidate in second_page.candidates] == [
        UUID(int=3),
        UUID(int=1),
    ]
    assert second_page.next_cursor == UserNotificationCandidateCursor(
        created_at=datetime(2026, 7, 2, 9, tzinfo=UTC),
        user_id=UUID(int=1),
    )


async def test_notification_candidates_return_empty_page_when_no_users(
    user_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with user_session_factory() as session:
        page = await SqlAlchemyUserRepository(session).list_notification_candidates(
            query=ListUserNotificationCandidatesQuery(as_of=AS_OF, batch_size=10)
        )

    assert page.candidates == ()
    assert page.next_cursor is None


async def test_notification_candidates_apply_created_at_policy_window(
    user_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with user_session_factory() as session:
        await _seed_users(
            session,
            (
                (1, datetime(2026, 7, 2, 9, tzinfo=UTC)),
                (2, datetime(2026, 6, 25, 9, tzinfo=UTC)),
                (3, datetime(2026, 6, 18, 9, tzinfo=UTC)),
            ),
        )

        page = await SqlAlchemyUserRepository(session).list_notification_candidates(
            query=ListUserNotificationCandidatesQuery(
                as_of=AS_OF,
                batch_size=10,
                created_after=datetime(2026, 6, 20, 0, tzinfo=UTC),
                created_before=datetime(2026, 7, 3, 0, tzinfo=UTC),
            )
        )

    assert [candidate.user_id for candidate in page.candidates] == [
        UUID(int=2),
        UUID(int=1),
    ]


async def test_notification_candidates_expose_policy_neutral_join_facts(
    user_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with user_session_factory() as session:
        await _seed_users(
            session,
            (
                (1, datetime(2026, 7, 2, 9, tzinfo=UTC)),
                (6, datetime(2026, 6, 29, 9, tzinfo=UTC)),
                (2, datetime(2026, 6, 25, 9, tzinfo=UTC)),
                (3, datetime(2026, 6, 18, 9, tzinfo=UTC)),
                (4, datetime(2026, 6, 11, 9, tzinfo=UTC)),
                (5, datetime(2026, 7, 3, 9, tzinfo=UTC)),
            ),
        )

        page = await SqlAlchemyUserRepository(session).list_notification_candidates(
            query=ListUserNotificationCandidatesQuery(as_of=AS_OF, batch_size=10)
        )

    assert [(candidate.user_id, candidate.days_since_joined) for candidate in page.candidates] == [
        (UUID(int=4), 28),
        (UUID(int=3), 21),
        (UUID(int=2), 14),
        (UUID(int=6), 10),
        (UUID(int=1), 7),
        (UUID(int=5), 6),
    ]


@pytest.mark.parametrize("batch_size", [0, -1])
def test_notification_candidate_query_rejects_invalid_batch_size(batch_size: int) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ListUserNotificationCandidatesQuery(as_of=AS_OF, batch_size=batch_size)

    assert _validation_details(exc_info.value) == (
        ("batchSize", "사용자 후보 조회 batchSize가 올바르지 않습니다."),
    )


def test_notification_candidate_query_rejects_invalid_cursor_datetime() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ListUserNotificationCandidatesQuery(
            as_of=AS_OF,
            batch_size=10,
            cursor=UserNotificationCandidateCursor(
                created_at=datetime(2026, 7, 2, 9),
                user_id=UUID(int=1),
            ),
        )

    assert _validation_details(exc_info.value) == (
        ("cursor", "사용자 후보 조회 cursor가 올바르지 않습니다."),
    )


def test_users_notification_candidate_query_has_no_notifications_dependency() -> None:
    offending_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in USERS_ROOT.rglob("*.py")
        if "tests" not in path.parts
        and any(
            imported == "app.modules.notifications"
            or imported.startswith("app.modules.notifications.")
            for imported in _imports(path)
        )
    ]

    assert offending_files == []


@pytest.fixture
async def user_session_factory(
    postgres_async_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(postgres_async_database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=_user_tables())

    try:
        yield build_session_factory(engine)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all, tables=_user_tables())
        await engine.dispose()


async def _seed_users(
    session: AsyncSession,
    rows: tuple[tuple[int, datetime], ...],
) -> None:
    for user_int, created_at in rows:
        session.add(
            orm.User(
                id=UUID(int=user_int),
                name=f"user-{user_int}",
                email=f"user-{user_int}@example.com",
                created_at=created_at,
                updated_at=created_at,
            )
        )
    await session.commit()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def _validation_details(error: ValidationError) -> tuple[tuple[str, str], ...]:
    return tuple((detail.field, detail.message) for detail in error.details)


def _user_tables() -> tuple[Table, ...]:
    user_table = orm.User.__table__
    if not isinstance(user_table, Table):
        raise AssertionError("users ORM table is not a SQLAlchemy Table")
    return (user_table,)

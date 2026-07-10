import ast
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Table, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.base import Base
from app.core.db.session import build_engine, build_session_factory
from app.modules.users.application.queries.get_existing_user_ids.query import (
    GetExistingUserIdsQuery,
)
from app.modules.users.application.queries.get_existing_user_ids.use_case import (
    GetExistingUserIdsQueryUseCase,
)
from app.modules.users.application.queries.list_user_registration_facts.query import (
    ListUserRegistrationFactsQuery,
)
from app.modules.users.application.queries.list_user_registration_facts.use_case import (
    ListUserRegistrationFactsQueryUseCase,
)
from app.modules.users.infrastructure.persistence import orm
from app.modules.users.infrastructure.persistence.existing_user_ids_reader import (
    SqlAlchemyExistingUserIdsReader,
)
from app.modules.users.infrastructure.persistence.user_registration_facts_reader import (
    SqlAlchemyUserRegistrationFactsReader,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
USERS_ROOT = PROJECT_ROOT / "app" / "modules" / "users"
OBSERVED_BEFORE = datetime(2026, 7, 10, tzinfo=UTC)


async def test_user_registration_facts_page_by_registered_at_and_id_cursor(
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
        use_case = _use_case(session)

        first_page = await use_case.execute(
            ListUserRegistrationFactsQuery(batch_size=2, observed_before=OBSERVED_BEFORE)
        )
        second_page = await use_case.execute(
            ListUserRegistrationFactsQuery(
                batch_size=2,
                observed_before=OBSERVED_BEFORE,
                cursor=first_page.next_cursor,
            )
        )

    assert [fact.user_id for fact in first_page.facts] == [UUID(int=4), UUID(int=2)]
    assert first_page.next_cursor is not None
    assert first_page.next_cursor.registered_at == datetime(2026, 6, 25, 9, tzinfo=UTC)
    assert first_page.next_cursor.user_id == UUID(int=2)
    assert [fact.user_id for fact in second_page.facts] == [UUID(int=3), UUID(int=1)]
    assert second_page.next_cursor is not None
    assert second_page.next_cursor.registered_at == datetime(2026, 7, 2, 9, tzinfo=UTC)
    assert second_page.next_cursor.user_id == UUID(int=1)


async def test_user_registration_facts_return_empty_page_when_no_users(
    user_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with user_session_factory() as session:
        page = await _use_case(session).execute(
            ListUserRegistrationFactsQuery(batch_size=10, observed_before=OBSERVED_BEFORE)
        )

    assert page.facts == ()
    assert page.next_cursor is None


async def test_user_registration_facts_keep_inclusive_lower_and_exclusive_observation_cutoff(
    user_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    lower_bound = datetime(2026, 6, 25, 9, tzinfo=UTC)
    observed_before = datetime(2026, 7, 2, 9, tzinfo=UTC)
    async with user_session_factory() as session:
        await _seed_users(session, ((1, lower_bound), (2, observed_before)))

        page = await _use_case(session).execute(
            ListUserRegistrationFactsQuery(
                batch_size=10,
                registered_after=lower_bound,
                observed_before=observed_before,
            )
        )

    assert [fact.user_id for fact in page.facts] == [UUID(int=1)]


async def test_existing_user_ids_excludes_withdrawn_user(
    user_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    active_user_id = UUID(int=1)
    withdrawn_user_id = UUID(int=2)
    async with user_session_factory() as session:
        await _seed_users(
            session,
            (
                (1, datetime(2026, 7, 1, 9, tzinfo=UTC)),
                (2, datetime(2026, 7, 1, 9, tzinfo=UTC)),
            ),
        )
        await session.execute(delete(orm.User).where(orm.User.id == withdrawn_user_id))
        result = await GetExistingUserIdsQueryUseCase(
            reader=SqlAlchemyExistingUserIdsReader(session)
        ).execute(GetExistingUserIdsQuery(user_ids=(active_user_id, withdrawn_user_id)))

    assert result.user_ids == frozenset({active_user_id})


def test_user_registration_facts_query_has_no_notifications_dependency() -> None:
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


def _use_case(session: AsyncSession) -> ListUserRegistrationFactsQueryUseCase:
    return ListUserRegistrationFactsQueryUseCase(
        reader=SqlAlchemyUserRegistrationFactsReader(session),
    )


async def _seed_users(
    session: AsyncSession,
    rows: tuple[tuple[int, datetime], ...],
) -> None:
    for user_int, registered_at in rows:
        session.add(
            orm.User(
                id=UUID(int=user_int),
                name=f"user-{user_int}",
                email=f"user-{user_int}@example.com",
                created_at=registered_at,
                updated_at=registered_at,
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


def _user_tables() -> tuple[Table, ...]:
    user_table = orm.User.__table__
    if not isinstance(user_table, Table):
        raise AssertionError("users ORM table is not a SQLAlchemy Table")
    return (user_table,)

from collections.abc import AsyncGenerator
from types import SimpleNamespace, TracebackType
from typing import cast

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_async_session
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.closed = True

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def build_request(session: FakeSession) -> Request:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                session_factory=lambda: session,
            )
        )
    )
    return cast(Request, request)


async def test_core_async_session_dependency_does_not_commit_after_success() -> None:
    session = FakeSession()
    session_dependency = cast(
        AsyncGenerator[AsyncSession, None],
        get_async_session(build_request(session)),
    )

    yielded_session = await anext(session_dependency)
    assert yielded_session is session
    with pytest.raises(StopAsyncIteration):
        await anext(session_dependency)

    assert session.commit_count == 0
    assert session.rollback_count == 0
    assert session.closed is True


async def test_core_async_session_dependency_closes_on_failure_without_rollback() -> None:
    session = FakeSession()
    session_dependency = cast(
        AsyncGenerator[AsyncSession, None],
        get_async_session(build_request(session)),
    )

    yielded_session = await anext(session_dependency)
    assert yielded_session is session
    with pytest.raises(RuntimeError, match="signup failed"):
        await session_dependency.athrow(RuntimeError("signup failed"))

    assert session.commit_count == 0
    assert session.rollback_count == 0
    assert session.closed is True


async def test_sqlalchemy_unit_of_work_commits_before_response_boundary() -> None:
    session = FakeSession()
    unit_of_work = SqlAlchemyUnitOfWork(cast(AsyncSession, session))

    await unit_of_work.commit()

    assert session.commit_count == 1
    assert session.rollback_count == 0

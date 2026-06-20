from collections.abc import AsyncGenerator
from types import SimpleNamespace, TracebackType
from typing import cast

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.dependencies import get_auth_transaction_session


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


async def test_auth_transaction_session_commits_after_success() -> None:
    session = FakeSession()
    transaction_session = cast(
        AsyncGenerator[AsyncSession, None],
        get_auth_transaction_session(build_request(session)),
    )

    yielded_session = await anext(transaction_session)
    assert yielded_session is session
    with pytest.raises(StopAsyncIteration):
        await anext(transaction_session)

    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.closed is True


async def test_auth_transaction_session_rolls_back_on_failure() -> None:
    session = FakeSession()
    transaction_session = cast(
        AsyncGenerator[AsyncSession, None],
        get_auth_transaction_session(build_request(session)),
    )

    yielded_session = await anext(transaction_session)
    assert yielded_session is session
    with pytest.raises(RuntimeError, match="signup failed"):
        await transaction_session.athrow(RuntimeError("signup failed"))

    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.closed is True

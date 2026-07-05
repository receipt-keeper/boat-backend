from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def request_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """request가 속한 app의 session factory를 반환한다.

    `app.state.session_factory` attribute 접근을 core 레이어로 캡슐화해,
    module-owned 코드가 session factory를 직접 다루지 않도록 한다
    (tests/test_db_session_architecture.py의 아키텍처 제약).
    """
    return request.app.state.session_factory  # type: ignore[no-any-return]


@asynccontextmanager
async def request_async_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request_session_factory(request)() as session:
        yield session


async def get_async_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request_async_session(request) as session:
        yield session


AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]

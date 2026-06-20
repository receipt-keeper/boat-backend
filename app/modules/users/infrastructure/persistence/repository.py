from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.users.application.ports.user_repository import UserRepository
from app.modules.users.domain.model import User
from app.modules.users.infrastructure.persistence import mapper, orm

SessionProvider = AsyncSession | async_sessionmaker[AsyncSession]


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session_provider: SessionProvider) -> None:
        self._session_provider = session_provider

    async def create(self, *, name: str | None, email: str | None) -> User:
        user = User.create(name=name, email=email)
        async with self._session(transactional=True) as session:
            record = mapper.user_to_record(user)
            session.add(record)
            await session.flush()
        return user

    async def delete_by_id(self, *, user_id: UUID) -> None:
        async with self._session(transactional=True) as session:
            await session.execute(delete(orm.User).where(orm.User.id == user_id))

    @asynccontextmanager
    async def _session(self, *, transactional: bool) -> AsyncIterator[AsyncSession]:
        if isinstance(self._session_provider, AsyncSession):
            yield self._session_provider
            return

        async with self._session_provider() as session:
            if not transactional:
                yield session
                return
            async with session.begin():
                yield session

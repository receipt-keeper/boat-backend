from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.domain.model import User
from app.modules.users.infrastructure.persistence import orm
from app.modules.users.infrastructure.persistence.repository import SqlAlchemyUserRepository


async def create_persisted_user(
    session: AsyncSession,
    *,
    name: str | None,
    email: str | None,
) -> User:
    return await SqlAlchemyUserRepository(session).create(name=name, email=email)


async def count_persisted_users(session: AsyncSession) -> int:
    count = await session.scalar(select(func.count()).select_from(orm.User))
    if count is None:
        raise AssertionError("PostgreSQL COUNT returned no value")
    return count


async def persisted_user_exists(session: AsyncSession, user_id: UUID) -> bool:
    return await session.get(orm.User, user_id) is not None

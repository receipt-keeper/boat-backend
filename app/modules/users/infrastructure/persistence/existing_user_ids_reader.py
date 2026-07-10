from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.application.queries.get_existing_user_ids.query import (
    GetExistingUserIdsQuery,
)
from app.modules.users.application.queries.get_existing_user_ids.reader import (
    ExistingUserIdsReader,
)
from app.modules.users.application.queries.get_existing_user_ids.result import ExistingUserIds
from app.modules.users.infrastructure.persistence import orm


class SqlAlchemyExistingUserIdsReader(ExistingUserIdsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_existing_user_ids(
        self,
        *,
        query: GetExistingUserIdsQuery,
    ) -> ExistingUserIds:
        if not query.user_ids:
            return ExistingUserIds(user_ids=frozenset())
        user_ids = await self._session.scalars(
            select(orm.User.id).where(orm.User.id.in_(query.user_ids))
        )
        return ExistingUserIds(user_ids=frozenset(user_ids))

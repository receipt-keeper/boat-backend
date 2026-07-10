from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.application.queries.list_user_registration_facts.query import (
    ListUserRegistrationFactsQuery,
    UserRegistrationFactCursor,
)
from app.modules.users.application.queries.list_user_registration_facts.reader import (
    UserRegistrationFactsReader,
)
from app.modules.users.application.queries.list_user_registration_facts.result import (
    UserRegistrationFact,
    UserRegistrationFactsPage,
)
from app.modules.users.infrastructure.persistence import orm


class SqlAlchemyUserRegistrationFactsReader(UserRegistrationFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_registration_facts(
        self,
        *,
        query: ListUserRegistrationFactsQuery,
    ) -> UserRegistrationFactsPage:
        statement = (
            select(orm.User)
            .order_by(orm.User.created_at.asc(), orm.User.id.asc())
            .limit(query.batch_size + 1)
        )
        if query.registered_after is not None:
            statement = statement.where(orm.User.created_at >= query.registered_after)
        if query.registered_before is not None:
            statement = statement.where(orm.User.created_at < query.registered_before)
        if query.cursor is not None:
            statement = statement.where(
                or_(
                    orm.User.created_at > query.cursor.registered_at,
                    and_(
                        orm.User.created_at == query.cursor.registered_at,
                        orm.User.id > query.cursor.user_id,
                    ),
                )
            )

        records = tuple((await self._session.execute(statement)).scalars().all())
        page_records = records[: query.batch_size]
        next_cursor = (
            UserRegistrationFactCursor(
                registered_at=page_records[-1].created_at,
                user_id=page_records[-1].id,
            )
            if len(records) > query.batch_size and page_records
            else None
        )
        return UserRegistrationFactsPage(
            facts=tuple(
                UserRegistrationFact(
                    user_id=record.id,
                    registered_at=record.created_at,
                )
                for record in page_records
            ),
            next_cursor=next_cursor,
        )

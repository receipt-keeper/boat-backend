from app.modules.users.application.queries.list_user_registration_facts.query import (
    ListUserRegistrationFactsQuery,
)
from app.modules.users.application.queries.list_user_registration_facts.reader import (
    UserRegistrationFactsReader,
)
from app.modules.users.application.queries.list_user_registration_facts.result import (
    UserRegistrationFactsPage,
)


class ListUserRegistrationFactsQueryUseCase:
    def __init__(self, *, reader: UserRegistrationFactsReader) -> None:
        self._reader = reader

    async def execute(
        self,
        query: ListUserRegistrationFactsQuery,
    ) -> UserRegistrationFactsPage:
        return await self._reader.list_registration_facts(query=query)

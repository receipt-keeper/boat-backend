from app.modules.users.application.queries.get_existing_user_ids.query import (
    GetExistingUserIdsQuery,
)
from app.modules.users.application.queries.get_existing_user_ids.reader import (
    ExistingUserIdsReader,
)
from app.modules.users.application.queries.get_existing_user_ids.result import ExistingUserIds


class GetExistingUserIdsQueryUseCase:
    def __init__(self, *, reader: ExistingUserIdsReader) -> None:
        self._reader = reader

    async def execute(self, query: GetExistingUserIdsQuery) -> ExistingUserIds:
        return await self._reader.get_existing_user_ids(query=query)

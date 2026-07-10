from dataclasses import dataclass
from uuid import UUID

from app.modules.users.application.queries.get_existing_user_ids.query import (
    GetExistingUserIdsQuery,
)
from app.modules.users.application.queries.get_existing_user_ids.reader import (
    ExistingUserIdsReader,
)
from app.modules.users.application.queries.get_existing_user_ids.result import ExistingUserIds
from app.modules.users.application.queries.get_existing_user_ids.use_case import (
    GetExistingUserIdsQueryUseCase,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000101")


@dataclass
class _ExistingUserIdsReader(ExistingUserIdsReader):
    result: ExistingUserIds
    received_query: GetExistingUserIdsQuery | None = None

    async def get_existing_user_ids(
        self,
        *,
        query: GetExistingUserIdsQuery,
    ) -> ExistingUserIds:
        self.received_query = query
        return self.result


async def test_get_existing_user_ids_returns_reader_result() -> None:
    query = GetExistingUserIdsQuery(user_ids=(USER_ID,))
    expected = ExistingUserIds(user_ids=frozenset({USER_ID}))
    reader = _ExistingUserIdsReader(result=expected)

    result = await GetExistingUserIdsQueryUseCase(reader=reader).execute(query)

    assert result == expected
    assert reader.received_query == query

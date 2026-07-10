from typing import Protocol

from app.modules.users.application.queries.get_existing_user_ids.query import (
    GetExistingUserIdsQuery,
)
from app.modules.users.application.queries.get_existing_user_ids.result import ExistingUserIds


class ExistingUserIdsReader(Protocol):
    async def get_existing_user_ids(
        self,
        *,
        query: GetExistingUserIdsQuery,
    ) -> ExistingUserIds: ...

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DeleteUserPushTokensCommand:
    user_id: UUID

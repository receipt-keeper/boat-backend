from typing import ClassVar
from uuid import UUID

from app.modules.examples.domain.model import ExampleUser


class ExampleUserRepository:
    _users: ClassVar[dict[UUID, ExampleUser]] = {}

    async def get(self, example_user_id: UUID) -> ExampleUser | None:
        return self._users.get(example_user_id)

    async def save(self, example_user: ExampleUser) -> ExampleUser:
        self._users[example_user.id] = example_user
        return example_user

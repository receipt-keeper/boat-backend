from typing import ClassVar
from uuid import UUID, uuid4

from app.modules.examples.domain.example_user import ExampleUser


class ExampleUserRepository:
    _users: ClassVar[dict[UUID, ExampleUser]] = {}

    async def get(self, example_user_id: UUID) -> ExampleUser | None:
        return self._users.get(example_user_id)

    async def create(self, *, nickname: str, email: str) -> ExampleUser:
        example_user = ExampleUser(
            id=uuid4(),
            nickname=nickname,
            email=email,
        )
        self._users[example_user.id] = example_user
        return example_user

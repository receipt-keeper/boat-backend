from uuid import UUID

from app.modules.examples.domain.exceptions import ExampleUserNotFoundError
from app.modules.examples.domain.model import ExampleUser
from app.modules.examples.infrastructure.repository import ExampleUserRepository


class ExampleUserService:
    def __init__(self, repository: ExampleUserRepository) -> None:
        self._repository = repository

    async def get_example_user(self, example_user_id: UUID) -> ExampleUser:
        example_user = await self._repository.get(example_user_id)
        if example_user is None:
            raise ExampleUserNotFoundError(example_user_id)

        return example_user

    async def create_example_user(self, *, nickname: str, email: str, password: str) -> ExampleUser:
        example_user = ExampleUser.create(nickname=nickname, email=email, password=password)
        return await self._repository.save(example_user)

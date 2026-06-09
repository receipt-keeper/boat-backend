from uuid import UUID

from app.core.http.exceptions import AppError
from app.modules.examples.domain.example_user import ExampleUser
from app.modules.examples.infrastructure.repository import ExampleUserRepository


class ExampleUserService:
    def __init__(self, repository: ExampleUserRepository) -> None:
        self._repository = repository

    async def get_example_user(self, example_user_id: UUID) -> ExampleUser:
        example_user = await self._repository.get(example_user_id)
        if example_user is None:
            raise AppError("예시 사용자를 찾을 수 없습니다.", status_code=404)

        return example_user

    async def create_example_user(self, *, nickname: str, email: str) -> ExampleUser:
        return await self._repository.create(nickname=nickname, email=email)

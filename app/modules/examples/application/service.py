from uuid import UUID

from app.core.application.event_dispatcher import EventDispatcher
from app.modules.examples.domain.exceptions import ExampleUserNotFoundError
from app.modules.examples.domain.model import ExampleUser
from app.modules.examples.infrastructure.repository import ExampleUserRepository


class ExampleUserService:
    def __init__(
        self,
        repository: ExampleUserRepository,
        event_dispatcher: EventDispatcher,
    ) -> None:
        self._repository = repository
        self._event_dispatcher = event_dispatcher

    async def get_example_user(self, example_user_id: UUID) -> ExampleUser:
        example_user = await self._repository.get(example_user_id)
        if example_user is None:
            raise ExampleUserNotFoundError(example_user_id)

        return example_user

    async def create_example_user(self, *, nickname: str, email: str, password: str) -> ExampleUser:
        example_user = ExampleUser.create(nickname=nickname, email=email, password=password)
        saved_user = await self._repository.save(example_user)
        await self._event_dispatcher.dispatch(saved_user.pull_events())
        return saved_user

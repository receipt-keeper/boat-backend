from typing import Annotated

from fastapi import Depends

from app.core.application.event_dispatcher import EventDispatcher
from app.modules.examples.application.service import ExampleUserService
from app.modules.examples.infrastructure.repository import ExampleUserRepository


async def get_example_user_repository() -> ExampleUserRepository:
    return ExampleUserRepository()


async def get_event_dispatcher() -> EventDispatcher:
    return EventDispatcher()


async def get_example_user_service(
    repository: Annotated[
        ExampleUserRepository,
        Depends(get_example_user_repository),
    ],
    event_dispatcher: Annotated[
        EventDispatcher,
        Depends(get_event_dispatcher),
    ],
) -> ExampleUserService:
    return ExampleUserService(repository, event_dispatcher)


ExampleUserServiceDep = Annotated[
    ExampleUserService,
    Depends(get_example_user_service),
]

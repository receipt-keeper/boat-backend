from typing import Annotated

from fastapi import Depends

from app.modules.examples.application.service import ExampleUserService
from app.modules.examples.infrastructure.repository import ExampleUserRepository


async def get_example_user_repository() -> ExampleUserRepository:
    return ExampleUserRepository()


async def get_example_user_service(
    repository: Annotated[
        ExampleUserRepository,
        Depends(get_example_user_repository),
    ],
) -> ExampleUserService:
    return ExampleUserService(repository)


ExampleUserServiceDep = Annotated[
    ExampleUserService,
    Depends(get_example_user_service),
]

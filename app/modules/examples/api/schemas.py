from uuid import UUID

from app.core.http.responses import AppBaseModel


class ExampleUserResponse(AppBaseModel):
    id: UUID
    nickname: str
    email: str


class CreateExampleUserRequest(AppBaseModel):
    nickname: str
    email: str
    password: str

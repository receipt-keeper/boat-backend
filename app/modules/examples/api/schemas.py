from uuid import UUID

from pydantic import Field, field_validator

from app.core.http.responses import AppBaseModel


class ExampleUserResponse(AppBaseModel):
    id: UUID
    nickname: str
    email: str


class CreateExampleUserRequest(AppBaseModel):
    nickname: str = Field(min_length=1, max_length=64)
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_must_look_valid(cls, value: str) -> str:
        if "@" not in value or "." not in value.rsplit("@", maxsplit=1)[-1]:
            raise ValueError("이메일 형식이 올바르지 않습니다.")
        return value

    @field_validator("password")
    @classmethod
    def password_must_be_long_enough(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다.")
        return value

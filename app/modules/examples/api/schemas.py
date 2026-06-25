from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class ExampleUserResponse(AppBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "00000000-0000-0000-0000-000000000401",
                    "nickname": "created-user",
                    "email": "created@example.com",
                }
            ]
        }
    )

    id: UUID = Field(description="예시 사용자 ID.")
    nickname: str = Field(description="닉네임.")
    email: str = Field(description="이메일.")


class CreateExampleUserRequest(AppBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "nickname": "created-user",
                    "email": "created@example.com",
                    "password": "password123",
                }
            ]
        }
    )

    nickname: str = Field(description="닉네임.")
    email: str = Field(description="이메일.")
    password: str = Field(description="비밀번호.")

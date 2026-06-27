from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class CurrentUserResponse(AppBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "name": "홍길동",
                    "nickname": "길동",
                    "profileImageUrl": "/api/v1/files/00000000-0000-0000-0000-000000000301/content",
                    "marketingConsent": False,
                }
            ]
        },
    )

    email: str | None = Field(
        alias="email",
        description="사용자의 대표 이메일.",
    )
    name: str | None = Field(
        alias="name",
        description="이름.",
    )
    nickname: str | None = Field(
        alias="nickname",
        description="닉네임.",
    )
    profile_image_url: str | None = Field(
        alias="profileImageUrl",
        description="프로필 이미지 경로.",
    )
    marketing_consent: bool = Field(
        alias="marketingConsent",
        description="마케팅 수신 동의 여부.",
    )


class UpdateCurrentUserRequest(AppBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "marketingConsent": True,
                }
            ]
        },
    )

    marketing_consent: bool | None = Field(
        default=None,
        alias="marketingConsent",
        description="마케팅 수신 동의 여부. 보내지 않으면 기존 값을 유지한다.",
    )


class UpdateCurrentUserResponse(AppBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "marketingConsent": True,
                }
            ]
        },
    )

    marketing_consent: bool = Field(
        alias="marketingConsent",
        description="반영된 마케팅 수신 동의.",
    )


class SetProfileImageRequest(AppBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={"examples": [{"fileId": "00000000-0000-0000-0000-000000000301"}]},
    )

    file_id: UUID = Field(
        alias="fileId",
        description="프로필 이미지로 설정할 업로드 파일 ID.",
    )


class ProfileImageResponse(AppBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"profileImageUrl": "/api/v1/files/00000000-0000-0000-0000-000000000301/content"}
            ]
        },
    )

    profile_image_url: str | None = Field(
        alias="profileImageUrl",
        description="프로필 이미지 경로.",
    )

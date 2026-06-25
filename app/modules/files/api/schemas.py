from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class UploadedFileResponse(AppBaseModel):
    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "fileId": "00000000-0000-0000-0000-000000000301",
                    "originalName": "profile.png",
                    "contentType": "image/png",
                    "size": 248120,
                    "contentPath": "/api/v1/files/00000000-0000-0000-0000-000000000301/content",
                }
            ]
        },
    )

    file_id: UUID = Field(alias="fileId", description="업로드된 파일 ID.")
    original_name: str = Field(alias="originalName", description="업로드 당시 파일명.")
    content_type: str = Field(alias="contentType", description="파일 형식.")
    size: int = Field(description="파일 크기.")
    content_path: str = Field(
        alias="contentPath",
        description="파일 다운로드 경로.",
    )


class FileMetadataResponse(UploadedFileResponse):
    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "fileId": "00000000-0000-0000-0000-000000000301",
                    "originalName": "profile.png",
                    "contentType": "image/png",
                    "size": 248120,
                    "contentPath": "/api/v1/files/00000000-0000-0000-0000-000000000301/content",
                    "purpose": "profile_image",
                    "status": "stored",
                }
            ]
        },
    )

    purpose: str = Field(description="파일 사용 목적.")
    status: str = Field(description="파일 상태.")

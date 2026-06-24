from uuid import UUID

from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class UploadedFileResponse(AppBaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    file_id: UUID = Field(alias="fileId")
    original_name: str = Field(alias="originalName")
    content_type: str = Field(alias="contentType")
    size: int
    content_path: str = Field(alias="contentPath")


class FileMetadataResponse(UploadedFileResponse):
    purpose: str
    status: str

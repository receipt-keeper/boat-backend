from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class AppBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CommonResponse[DataT](AppBaseModel):
    success: bool
    status: int
    data: DataT


class FieldError(AppBaseModel):
    field: str
    message: str


class ApiErrorData(AppBaseModel):
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    )
    message: str
    path: str
    errors: list[FieldError] = Field(default_factory=list)

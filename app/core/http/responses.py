from datetime import UTC, datetime

from pydantic import BaseModel, Field
from pydantic_core import ErrorDetails

_REQUEST_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}


class AppBaseModel(BaseModel):
    """모든 요청/응답 모델의 공통 베이스 — 전역 모델 설정의 단일 확장 지점."""


class CommonResponse[DataT](AppBaseModel):
    success: bool
    status: int
    data: DataT


class FieldError(AppBaseModel):
    field: str
    message: str

    @classmethod
    def from_pydantic_error(cls, error: ErrorDetails) -> "FieldError":
        location = error["loc"]
        if location and location[0] in _REQUEST_LOCATION_PREFIXES:
            location = location[1:]

        message = error["msg"]
        context = error.get("ctx")
        context_error = context.get("error") if context else None
        if isinstance(context_error, str):
            message = context_error
        elif isinstance(context_error, BaseException):
            message = str(context_error)

        return cls(
            field=".".join(str(part) for part in location),
            message=message,
        )


class ApiErrorData(AppBaseModel):
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    )
    message: str
    path: str
    errors: list[FieldError] = Field(default_factory=list)

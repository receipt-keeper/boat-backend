from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import ErrorDetails

_REQUEST_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}


class AppBaseModel(BaseModel):
    """모든 요청/응답 모델의 공통 베이스 — 전역 모델 설정의 단일 확장 지점."""


class CommonResponse[DataT](AppBaseModel):
    success: bool
    status: int
    data: DataT


class CursorPaginationResponse(AppBaseModel):
    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "nextCursor": "20",
                    "hasNext": True,
                    "limit": 20,
                    "totalCount": 42,
                }
            ]
        },
    )

    next_cursor: str | None = Field(
        default=None,
        alias="nextCursor",
        description="다음 목록을 조회할 때 cursor로 전달할 값. 마지막 목록이면 null이다.",
    )
    has_next: bool = Field(alias="hasNext", description="다음 목록 존재 여부.")
    limit: int = Field(description="이번 요청에 적용된 최대 조회 개수.")
    total_count: int | None = Field(
        default=None,
        alias="totalCount",
        description="현재 조건에 맞는 전체 개수. 계산하지 않는 목록이면 null이다.",
    )


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

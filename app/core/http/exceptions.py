from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDetail:
    field: str
    message: str


class AppError(Exception):
    """Base class for application-owned errors."""

    status_code = 400
    code = "app_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        errors: list[ErrorDetail] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code or self.status_code
        self.errors = errors or []
        super().__init__(message)

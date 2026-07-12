import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import Response

from app.core.http.responses import FieldError

logger = logging.getLogger(__name__)


class OcrDiagnosticRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        route_handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await route_handler(request)
            except RequestValidationError as exception:
                validation_errors = exception.errors()
                fields = tuple(
                    FieldError.from_pydantic_error(error).field for error in validation_errors
                )
                error_types = tuple(
                    str(error.get("type", "unknown")) for error in validation_errors
                )
                logger.warning(
                    "ocr_request_validation_failed path=%s fields=%s "
                    "error_types=%s exception_type=%s",
                    request.url.path,
                    fields,
                    error_types,
                    type(exception).__name__,
                )
                raise

        return handle

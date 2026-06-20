from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config.settings import Settings
from app.core.db.session import build_engine, build_session_factory
from app.core.domain.exceptions import (
    DomainError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.core.http import exception_handlers
from app.core.observability.health import router as observability_router
from app.modules.auth.api import exception_handlers as auth_exception_handlers
from app.modules.auth.api.router import router as auth_router
from app.modules.auth.domain.exceptions import AuthenticationError, AuthorizationError
from app.modules.examples.api.router import router as examples_router
from app.modules.ocr.api.router import router as ocr_router
from app.modules.users.api.router import router as users_router


def _register_exception_handlers(app: FastAPI) -> None:
    # 예외 클래스 → 핸들러 등록이 곧 의미 카테고리 → HTTP 상태 매핑이다 (subclass 핸들러 우선)
    app.add_exception_handler(ValidationError, exception_handlers.handle_domain_validation_error)
    app.add_exception_handler(NotFoundError, exception_handlers.handle_not_found_error)
    app.add_exception_handler(
        ExternalServiceError,
        exception_handlers.handle_external_service_error,
    )
    app.add_exception_handler(
        AuthenticationError,
        auth_exception_handlers.handle_authentication_error,
    )
    app.add_exception_handler(
        AuthorizationError,
        auth_exception_handlers.handle_authorization_error,
    )
    app.add_exception_handler(DomainError, exception_handlers.handle_domain_error)
    app.add_exception_handler(
        RequestValidationError,
        exception_handlers.handle_request_validation_error,
    )
    app.add_exception_handler(
        StarletteHTTPException,
        exception_handlers.handle_http_exception,
    )
    app.add_exception_handler(Exception, exception_handlers.handle_unexpected_error)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(resolved_settings.database_url)
        _app.state.engine = engine
        _app.state.session_factory = build_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        docs_url=resolved_settings.docs_url,
        redoc_url=resolved_settings.redoc_url,
        openapi_url=resolved_settings.openapi_url,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.include_router(auth_router, prefix=resolved_settings.api_prefix)
    app.include_router(users_router, prefix=resolved_settings.api_prefix)
    app.include_router(examples_router, prefix=resolved_settings.api_prefix)
    app.include_router(ocr_router, prefix=resolved_settings.api_prefix)
    app.include_router(observability_router)
    _register_exception_handlers(app)

    return app


app = create_app()

__all__ = ["app", "create_app"]

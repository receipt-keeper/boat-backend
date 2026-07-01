from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config.settings import Settings
from app.core.db.session import build_engine, build_session_factory
from app.core.domain.exceptions import (
    ConflictError,
    DomainError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.core.http import exception_handlers
from app.core.observability.health import router as observability_router
from app.modules.auth.api import exception_handlers as auth_exception_handlers
from app.modules.auth.api.router import router as auth_router
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.auth.domain.exceptions import AuthenticationError, AuthorizationError
from app.modules.credits.api.router import router as credits_router
from app.modules.example.api.router import router as example_router
from app.modules.files.api.router import router as files_router
from app.modules.files.dependencies import get_file_reference_guard
from app.modules.notifications.api.router import router as notifications_router
from app.modules.ocr.api import exception_handlers as ocr_exception_handlers
from app.modules.ocr.api.router import router as ocr_router
from app.modules.ocr.domain.exceptions import ReceiptOcrProviderUnavailableError
from app.modules.receipts.api.router import router as receipts_router
from app.modules.usage.api.router import router as usage_router
from app.modules.users.api.router import router as users_router
from app.modules.users.dependencies import get_profile_image_file_reference_guard


def _register_exception_handlers(app: FastAPI) -> None:
    # 예외 클래스 → 핸들러 등록이 곧 의미 카테고리 → HTTP 상태 매핑이다 (subclass 핸들러 우선)
    app.add_exception_handler(ValidationError, exception_handlers.handle_domain_validation_error)
    app.add_exception_handler(NotFoundError, exception_handlers.handle_not_found_error)
    app.add_exception_handler(ConflictError, exception_handlers.handle_conflict_error)
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
    app.add_exception_handler(
        ReceiptOcrProviderUnavailableError,
        ocr_exception_handlers.handle_receipt_ocr_provider_unavailable_error,
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
    app.dependency_overrides[get_file_reference_guard] = get_profile_image_file_reference_guard
    app.include_router(auth_router, prefix=resolved_settings.api_prefix)
    app.include_router(
        users_router,
        prefix=resolved_settings.api_prefix,
        dependencies=[Depends(authenticate_current_principal)],
    )
    app.include_router(
        files_router,
        prefix=resolved_settings.api_prefix,
        dependencies=[Depends(authenticate_current_principal)],
    )
    app.include_router(
        ocr_router,
        prefix=resolved_settings.api_prefix,
        dependencies=[Depends(authenticate_current_principal)],
    )
    app.include_router(
        receipts_router,
        prefix=resolved_settings.api_prefix,
        dependencies=[Depends(authenticate_current_principal)],
    )
    app.include_router(
        credits_router,
        prefix=resolved_settings.api_prefix,
        dependencies=[Depends(authenticate_current_principal)],
    )
    app.include_router(example_router, prefix=resolved_settings.api_prefix)
    app.include_router(
        notifications_router,
        prefix=resolved_settings.api_prefix,
        dependencies=[Depends(authenticate_current_principal)],
    )
    app.include_router(
        usage_router,
        prefix=resolved_settings.api_prefix,
        dependencies=[Depends(authenticate_current_principal)],
    )
    app.include_router(observability_router)
    _register_exception_handlers(app)

    return app


app = create_app()

__all__ = ["app", "create_app"]

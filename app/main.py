from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config.settings import Settings
from app.core.db.session import build_engine, build_session_factory
from app.core.http.exception_handlers import register_exception_handlers
from app.core.observability.health import router as observability_router
from app.modules.examples.api.router import router as examples_router


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
    app.include_router(examples_router, prefix=resolved_settings.api_prefix)
    app.include_router(observability_router)
    register_exception_handlers(app)

    return app


app = create_app()

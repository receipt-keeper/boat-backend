# CORE KNOWLEDGE BASE

## OVERVIEW

Shared platform layer. Domain modules may import `app.core`; `app.core` must not import domain modules.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Settings | `config/settings.py` | Pydantic Settings and cached `get_settings()`. |
| Request settings | `config/dependencies.py` | Reads `request.app.state.settings`. |
| SQLAlchemy base | `db/base.py` | Naming convention for Alembic autogenerate. |
| Engine/session builders | `db/session.py` | Builders only; lifecycle is in `app/main.py`. |
| Domain bases | `domain/` | Entity, value object, event, exceptions, validation aggregation. |
| Response envelope | `http/responses.py` | `CommonResponse`, `ApiErrorData`, `FieldError`. |
| Exception handlers | `http/exception_handlers.py` | Error envelope conversion and logging. |
| Event dispatch | `application/event_dispatcher.py` | Same-process dispatch, no durability contract. |
| Health | `observability/health.py` | Liveness endpoint only. |
| Core contracts | `tests/` | Core behavior tests live beside core code. |

## CONVENTIONS

- Keep this layer domain-neutral. Names here should make sense across modules.
- Add environment variables as `Settings` fields; callers should receive settings through app state or DI.
- ORM models outside core must inherit `Base`; do not define alternate declarative bases.
- Domain exception classes express meaning only. HTTP mapping belongs in `http/exception_handlers.py` and `app/main.py`.
- `ValidationError` should carry aggregated `ErrorDetail` values; use `Notification` when collecting multiple field failures.
- `FieldError.from_pydantic_error()` owns request-validation field normalization.
- `EventDispatcher` is an in-process utility only; do not imply outbox, retry, replay, or broker semantics.

## ANTI-PATTERNS

- Do not import `app.modules.*` from core.
- Do not put module-specific values, tables, providers, or routers in core.
- Do not let core domain primitives know about FastAPI, SQLAlchemy, or HTTP status codes.
- Do not move engine/session lifecycle into `db/session.py`; it stays in app lifespan.
- Do not add security/provider helpers here just because multiple modules might use them later.

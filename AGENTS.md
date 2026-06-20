# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-20 04:12:06 +0900
**Commit:** b8f2346
**Branch:** 58-21-소셜-로그인-및-JWT-인증-구현

## OVERVIEW

Receipt Keeper backend API. FastAPI + SQLAlchemy 2.0 async + PostgreSQL(asyncpg) + Alembic, Python 3.12, uv-managed.

This repo is a strict domain-module monolith: `app/main.py` is the composition root, `app/core` is shared platform code, and `app/modules/<domain>` owns vertical slices.

## STRUCTURE

```text
boat-backend/
├── app/main.py                  # create_app(), lifespan DB state, routers, exception handlers
├── app/core/                    # shared config/db/domain/http/application/observability primitives
├── app/modules/                 # domain modules: auth, users, examples
├── alembic/                     # async migration env + generated versions
├── tests/                       # app-level integration tests
├── conftest.py                  # shared httpx ASGI client fixture
├── pyproject.toml               # ruff, pyright, pytest, coverage config
└── Makefile                     # canonical local commands
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| App wiring | `app/main.py` | Keep router/handler registration here; no `app/composition` package. |
| Runtime settings | `app/core/config/settings.py` | Add env vars to `Settings`; do not read `os.environ` directly. |
| DB lifecycle | `app/core/db/session.py`, `app/main.py` | Engine/session factory are created in lifespan and stored on `app.state`. |
| Error envelope | `app/core/http/exception_handlers.py` | Domain category to HTTP status mapping lives here and in `app/main.py`. |
| Shared domain primitives | `app/core/domain/` | `Entity`, `ValueObject`, `DomainError`, `Notification`, events. |
| Auth | `app/modules/auth/` | Firebase identity -> backend access/refresh tokens. |
| Users | `app/modules/users/` | Provisioning-only module today; no public users API. |
| Example module | `app/modules/examples/` | Reference/demo slice; in-memory repository is not production pattern. |
| App tests | `tests/` | Health, OpenAPI, lifespan, global error envelope. |
| Module tests | `app/modules/<name>/tests/` | Module-owned API, service, architecture, and fixture tests. |

## CODE MAP

Live codegraph was not available in this session; this map is from ast-grep plus static `rg`.

| Symbol | Type | Location | Refs | Role |
|---|---|---:|---:|---|
| `create_app` | function | `app/main.py` | high | App factory and composition root. |
| `_register_exception_handlers` | function | `app/main.py` | local | Meaning category to HTTP handler registration. |
| `Settings` | class | `app/core/config/settings.py` | high | Runtime configuration SSOT. |
| `Base` | class | `app/core/db/base.py` | medium | SQLAlchemy metadata naming convention. |
| `CommonResponse` / `ApiErrorData` | models | `app/core/http/responses.py` | high | Success/failure response envelope. |
| `Notification` | class | `app/core/domain/validation.py` | medium | Aggregates field validation failures. |
| `EventDispatcher` | class | `app/core/application/event_dispatcher.py` | medium | Same-process event dispatch only. |
| `LoginCommandUseCase` / `RefreshTokenCommandUseCase` | classes | `app/modules/auth/application/commands/` | high | Auth command orchestration. |
| `SqlAlchemyCredentialRepository` | class | `app/modules/auth/infrastructure/persistence/credential_repository.py` | medium | Auth persistence adapter. |
| `JwtAccessTokenService` | class | `app/modules/auth/infrastructure/tokens/jwt.py` | medium | Backend-issued access JWT adapter. |
| `ProvisionUserCommandUseCase` | class | `app/modules/users/application/commands/provision/use_case.py` | medium | Cross-module user provisioning contract consumed by auth. |

## CONVENTIONS

- Makefile targets are the primary interface: `make install`, `make lint`, `make format`, `make typecheck`, `make test`, `make check`.
- Add dependencies with `uv add <pkg>` or `uv add --dev <pkg>`; do not hand-edit dependency tables in `pyproject.toml`.
- Local server: `uv run fastapi dev app/main.py`.
- Migrations: `uv run alembic revision --autogenerate -m "..."` then `uv run alembic upgrade head`.
- API success responses use `CommonResponse[T]`; failures use `CommonResponse[ApiErrorData]`.
- Existing `POST /auth/logout` intentionally returns `204` with an empty body; keep tests and docs aligned if changing it.
- `RequestValidationError` and domain `ValidationError` both return 422. `NotFoundError` maps to 404, uncategorized `DomainError` to 400.
- Domain exceptions carry meaning, message, and context only. They do not own HTTP status codes.
- Field validation messages live with value objects; entity `create()` factories aggregate failures with `Notification`.
- User-facing domain and validation messages are Korean.
- Endpoint, service, and repository methods are async. Do not add blocking calls on request paths.
- Every function signature needs argument and return type hints; pyright is `standard`.
- ORM models inherit `app.core.db.base.Base` so Alembic names constraints deterministically.
- Tests use `asyncio_mode = "auto"`; async tests do not need decorators.
- Root `conftest.py` provides the in-process httpx ASGI `client`; module fixtures own dependency overrides.
- Production modules expose application command flows as `application/commands/<business_task>/{command.py,result.py?,use_case.py}` and internal read flows as `application/queries/<read_task>/{query.py,result.py?,use_case.py}`. Reserve `read_models` for public optimized read API/read model surfaces.

## ANTI-PATTERNS

- Do not create `app/composition`; module-owned `dependencies.py` files are the runtime wiring boundary.
- Do not put FastAPI, SQLAlchemy, provider SDKs, DB sessions, or concrete adapters in domain code.
- Do not let module application code import its own infrastructure or another module's infrastructure.
- Do not let auth import `app.modules.users.infrastructure`; auth may use users application command contracts and users dependencies.
- Do not put `status_code` on domain exceptions.
- Do not put validation rules in request schemas when they are domain rules.
- Do not add cross-BC database foreign keys; cross-BC references are UUID values.
- Do not use suffixes like `Record` just to explain persistence role; package path owns the role.
- Do not introduce command bus/query bus, event sourcing, outbox, external message bus, Kafka/RabbitMQ/Celery, separate read DB, read-store, projection worker, or materialized view without explicit later approval.
- Do not treat `docs/58-21-소셜-로그인-및-JWT-인증-구현/` as current policy when it conflicts with `ARCHITECTURE.md`, tests, or `docs/auth-hexagonal-completion/`.

## COMMANDS

```bash
make install
make lint
make format
make typecheck
make test
make check
uv run fastapi dev app/main.py
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

## NOTES

- `README.md` body is user-managed; only fix factual drift against code.
- Do not touch `docs/`, `.omc/`, or `.omx` unless the user explicitly asks.
- `app/modules/examples` is a reference/demo module. Its `ClassVar` in-memory repository is not the production repository pattern.
- `docs/auth-hexagonal-completion/` contains durable auth boundary decisions; branch planning docs contain historical and task-scoped material.
- `make check` is expected before commit.

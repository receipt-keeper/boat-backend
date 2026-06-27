# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-27 23:04:09 +0900
**Commit:** cd2da42
**Branch:** main

## OVERVIEW

Receipt Keeper 백엔드 API. FastAPI + SQLAlchemy 2.0 async + PostgreSQL(asyncpg) + Alembic, Python 3.12, uv 기반이다.

이 저장소는 도메인 모듈 기반 모놀리스다. `app/main.py`가 런타임 composition root이고, `app/core`는 공유 플랫폼 코드, `app/modules/<domain>`은 수직 도메인 슬라이스를 소유한다.

## STRUCTURE

```text
boat-backend/
├── app/main.py                  # create_app(), lifespan DB state, router wiring, exception handlers
├── app/core/                    # shared config/db/domain/http/security/application primitives
├── app/modules/                 # auth, users, files, receipts, ocr, credits, usage, notifications
├── alembic/                     # async migration env + generated versions
├── tests/                       # app-level and BC contract tests
├── conftest.py                  # shared httpx ASGI client fixture
├── pyproject.toml               # ruff, pyright, pytest, coverage config
├── Dockerfile                   # uv frozen prod image, uvicorn runtime
└── Makefile                     # canonical local commands
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| 앱 조립 | `app/main.py` | 라우터, handler, lifespan, app-level override를 여기서 등록한다. `app/composition`은 만들지 않는다. |
| 런타임 설정 | `app/core/config/settings.py` | env var는 `Settings`에 추가한다. `os.environ` 직접 읽기 금지. |
| DB lifecycle | `app/core/db/session.py`, `app/main.py` | engine/session factory는 lifespan에서 만들고 `app.state`에 둔다. |
| 요청 DB session | `app/core/db/session.py` | `AsyncSessionDep`가 request-scoped session dependency다. 모듈이 session scope를 소유하지 않는다. |
| Unit of work | `app/core/application/unit_of_work.py`, `app/core/db/unit_of_work.py` | port는 core/application, SQLAlchemy 구현은 core/db. |
| 에러 envelope | `app/core/http/exception_handlers.py` | 의미 카테고리에서 HTTP status로의 매핑은 여기와 `app/main.py`가 담당한다. |
| 인증 principal | `app/core/security/principal.py` | bearer principal은 core-owned다. auth application 아래로 되돌리지 않는다. |
| Auth | `app/modules/auth/` | 외부 identity를 검증하고 backend access JWT + opaque refresh token을 발급한다. |
| Users | `app/modules/users/` | mypage profile API, profile image, auth가 쓰는 provisioning/deletion contract. |
| Files | `app/modules/files/` | 업로드, 메타데이터, content streaming, delete guard, local object storage adapter. |
| Receipts | `app/modules/receipts/` | receipt aggregate와 create/list/read API. |
| OCR | `app/modules/ocr/` | 영수증 이미지 OCR boundary와 provider unavailable mapping. |
| Credits/usage/notifications | `app/modules/{credits,usage,notifications}/` | 현재 mock-backed app contract지만 API schema와 OpenAPI 문구는 각 모듈 소유. |
| App tests | `tests/` | health/OpenAPI/lifespan, DB session architecture, BC contract tests. |
| Module tests | `app/modules/<name>/tests/` | 모듈 소유 API, service, fixture, architecture tests. |

## CODE MAP

현재 map은 codegraph와 architecture tests 기준이다.

| Symbol | Type | Location | Refs | Role |
|---|---|---:|---:|---|
| `create_app` | function | `app/main.py` | high | App factory, lifespan, dependency overrides, router composition. |
| `_register_exception_handlers` | function | `app/main.py` | local | 의미 카테고리별 HTTP handler 등록. |
| `Settings` | class | `app/core/config/settings.py` | high | 런타임 설정 SSOT. file storage/JWT 설정 포함. |
| `AsyncSessionDep` | type alias | `app/core/db/session.py` | high | 요청 단위 SQLAlchemy session dependency. |
| `CommonResponse` / `ApiErrorData` | models | `app/core/http/responses.py` | high | 성공/실패 응답 envelope. |
| `AuthenticatedPrincipal` | model | `app/core/security/principal.py` | high | backend JWT에서 복원되는 core-owned principal. |
| `EventDispatcher` | class | `app/core/application/event_dispatcher.py` | medium | same-process event dispatch 전용. |
| `LoginCommandUseCase` / `RefreshTokenCommandUseCase` | classes | `app/modules/auth/application/commands/` | high | auth command orchestration. |
| `CurrentPrincipalQueryUseCase` | class | `app/modules/auth/application/queries/current_principal/use_case.py` | high | bearer access token 복원. |
| `WithdrawAccountCommandUseCase` | class | `app/modules/auth/application/commands/withdraw/use_case.py` | high | users withdrawal route가 위임하는 auth credential 삭제 흐름. |
| `ResolveUserForLoginCommandUseCase` | class | `app/modules/users/application/commands/resolve_user_for_login/use_case.py` | high | auth login이 쓰는 cross-module user contract. |
| `UpdateProfileImageCommandUseCase` | class | `app/modules/users/application/commands/update_profile_image/use_case.py` | medium | users profile image state와 file reference guard의 기준. |
| `UploadFileCommandUseCase` / `DeleteFileCommandUseCase` | classes | `app/modules/files/application/commands/` | high | repository, storage, unit of work를 통한 file write/delete 흐름. |
| `GetFileQueryUseCase` / `OpenFileContentQueryUseCase` | classes | `app/modules/files/application/queries/` | high | file metadata/content read 흐름. |
| `Receipt` | entity | `app/modules/receipts/domain/model.py` | medium | receipt aggregate와 warranty expiry 계산. |

## CONVENTIONS

- 로컬 표준 인터페이스는 Makefile이다: `make install`, `make lint`, `make format`, `make typecheck`, `make test`, `make check`.
- CI는 `uv sync --all-groups --frozen`로 설치한다. CI 통과가 필요하면 `uv.lock` 갱신 여부를 먼저 맞춘다.
- 의존성은 `uv add <pkg>` 또는 `uv add --dev <pkg>`로 추가한다. `pyproject.toml` dependency table을 손으로 편집하지 않는다.
- 로컬 서버: `uv run fastapi dev app/main.py`.
- Docker build는 `uv sync --frozen --no-dev --no-install-project`를 사용하고, runtime은 `uvicorn app.main:app --host 0.0.0.0 --port 8000`이다.
- migration: `uv run alembic revision --autogenerate -m "..."` 후 `uv run alembic upgrade head`.
- API 성공 응답은 `CommonResponse[T]`, 실패 응답은 `CommonResponse[ApiErrorData]`를 쓴다.
- `204` endpoint는 본문 없이 반환한다. 변경 시 tests와 OpenAPI docs를 같이 맞춘다.
- `RequestValidationError`와 domain `ValidationError`는 422. `NotFoundError`는 404, `ConflictError`는 409, `ExternalServiceError`는 provider 상태, 미분류 `DomainError`는 400.
- Domain exception은 의미, message, context만 가진다. HTTP status를 소유하지 않는다.
- Field validation message는 value object가 소유하고, entity `create()` factory는 `Notification`으로 실패를 집계한다.
- 사용자 대면 domain/validation/OpenAPI contract 문구는 한글로 작성한다.
- endpoint, service, repository, storage, provider method는 async다. 로컬 파일 I/O나 sync provider SDK 호출은 event loop 밖으로 보낸다.
- 모든 함수 signature에는 argument와 return type hint를 둔다. pyright는 `standard`.
- ORM model은 `app.core.db.base.Base`를 상속해 Alembic constraint name을 결정적으로 만든다.
- tests는 `asyncio_mode = "auto"`다. async test에 decorator를 붙이지 않는다.
- `make test`는 coverage `fail_under = 82`와 warnings-as-errors를 강제한다.
- root `conftest.py`는 in-process httpx ASGI `client`를 제공한다. module fixture가 dependency override와 seeded helper를 소유한다.
- Production module의 command flow는 `application/commands/<business_task>/{command.py,result.py?,use_case.py}`로 둔다.
- 내부 side-effect-free read flow는 `application/queries/<read_task>/{query.py,result.py?,use_case.py}`로 둔다.
- `read_models`는 public optimized read API/read model surface가 필요할 때만 쓴다.
- 중요한 layout/import 규칙은 prose만 쓰지 말고 `tests/test_*architecture.py` 또는 `app/modules/<name>/tests/test_architecture.py`로 고정한다.

## ANTI-PATTERNS

- `app/composition`을 만들지 않는다. 런타임 wiring boundary는 module-owned `dependencies.py`다.
- domain code에 FastAPI, SQLAlchemy, provider SDK, DB session, concrete adapter를 넣지 않는다.
- module application code가 자기 module infrastructure 또는 다른 module infrastructure를 import하지 않는다.
- auth는 `app.modules.users.infrastructure`를 import하지 않는다. users application command contract와 users dependencies만 사용할 수 있다.
- users application/domain은 `app.modules.files.infrastructure`를 import하지 않는다. file ID와 module-owned guard를 사용한다.
- domain exception에 `status_code`를 넣지 않는다.
- domain rule을 request schema validation에 넣지 않는다.
- Cross-BC database foreign key를 추가하지 않는다. cross-BC reference는 UUID value다.
- persistence 역할 설명만을 위해 `Record` 같은 suffix를 붙이지 않는다. 역할은 package path가 설명한다.
- command bus/query bus, event sourcing, outbox, external message bus, Kafka/RabbitMQ/Celery, separate read DB, read-store, projection worker, materialized view는 명시 승인 전까지 도입하지 않는다.

## COMMANDS

```bash
make install
make lint
make format
make typecheck
make test
make check
uv sync --all-groups --frozen
uv run fastapi dev app/main.py
uv run alembic revision --autogenerate -m "message"
uv run alembic upgrade head
```

# 아키텍처

## 개요

boat-backend는 **도메인 모듈 기반 모놀리스**다. Netflix Dispatch 스타일로 도메인별 모듈(`app/modules/<도메인>`)을 수직으로 나누고, 각 모듈 내부는 클린 아키텍처 계층(api / application / domain / infrastructure)으로 구성한다. 공유 인프라는 `app/core`에 모은다.

- 스택: FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL(asyncpg) + Alembic, Python 3.12, 패키지 관리는 uv
- 앱 진입점: `app/main.py`의 `create_app()` 앱 팩토리 (`app = create_app()` 모듈 레벨 인스턴스도 제공)
- 품질 도구: ruff, pyright(standard), pytest(asyncio_mode=auto) — 실행은 `make lint` / `make typecheck` / `make test` (또는 `uv run ruff check`, `uv run pyright`, `uv run pytest`)

## 디렉토리 구조

```
app/
├── main.py                      # 앱 팩토리(create_app), lifespan, 라우터/예외 핸들러 등록
├── core/                        # 모듈 간 공유 인프라
│   ├── config/
│   │   └── settings.py          # pydantic-settings 기반 Settings, get_settings (lru_cache)
│   ├── db/
│   │   ├── base.py              # DeclarativeBase + naming convention 메타데이터
│   │   └── session.py           # build_engine, build_session_factory
│   ├── domain/
│   │   ├── entity.py            # Entity[IdT] 제네릭 베이스 (id 기반 동등성·해시)
│   │   ├── value_object.py      # ValueObject[ValueT] 추상 베이스 (생성 시 validate() 강제)
│   │   ├── exceptions.py        # DomainError 루트 + 의미 카테고리(ValidationError/NotFoundError), ErrorDetail
│   │   └── validation.py        # Notification (검증 실패 집계 — Fowler Notification 패턴)
│   ├── http/
│   │   ├── responses.py         # CommonResponse[DataT], ApiErrorData, FieldError
│   │   └── exception_handlers.py# 전역 예외 핸들러 함수 (예외 → 실패 envelope)
│   └── observability/
│       └── health.py            # GET /health
└── modules/
    └── examples/                # 데모/참조 모듈 (production package pattern source 아님)
        ├── api/
        │   ├── router.py        # APIRouter, 엔드포인트
        │   └── schemas.py       # 요청/응답 Pydantic 스키마 (전송 형태만 — 검증 규칙 없음)
        ├── application/
        │   └── service.py       # ExampleUserService (유스케이스)
        ├── domain/
        │   ├── model.py         # ExampleUser 엔티티 (create() 팩토리 — 검증 집계)
        │   ├── value_objects.py # 값 객체 (Nickname/Email/Password — 규칙·메시지 소유)
        │   └── exceptions.py    # 도메인 예외 — 의미 카테고리 상속, message+맥락만 소유 (HTTP 무지)
        ├── infrastructure/
        │   └── repository.py    # ExampleUserRepository (현재 in-memory)
        └── dependencies.py      # FastAPI Depends 체인 (repository → service)
alembic/
└── env.py                       # async 마이그레이션 (Base.metadata, settings.database_url 주입)
conftest.py                      # 공용 client fixture (전체 테스트에서 사용)
tests/
└── test_app.py                  # 앱 수준 통합 테스트 (health, lifespan, settings, OpenAPI)
app/core/tests/                  # core 베이스 계약 테스트 (Entity, FieldError)
app/modules/examples/tests/      # 모듈 소유 테스트 + 모듈 전용 override fixture
```

## 계층 구조와 의존 방향

```
api ──────────► application ──────────► domain ◄────────── infrastructure
(HTTP, 스키마)   (유스케이스, ports)      (엔티티, 도메인 예외)   (ports 구현)
                         ▲
                         └────────── dependencies.py가 concrete adapter wiring
```

| 계층 | 역할 | 의존 가능 대상 |
|---|---|---|
| `api` | 라우터, 요청/응답 스키마, HTTP 상태 코드 매핑 | application, core/http |
| `application` | command/query use case 조합 — 도메인 로직(팩토리·값 객체)을 조립하고 application port contract를 호출한다 | domain, application ports, core/application primitives |
| `domain` | 엔티티(생성 팩토리), 값 객체, 도메인 예외 — 검증·생성 규칙의 유일한 소유자 | **없음** (core/domain의 베이스만 상속) |
| `infrastructure` | 영속성·provider adapter — application ports contract를 구현한다 | domain, application ports contract, core/db |

규칙:

- **domain은 무엇에도 의존하지 않는다.** 프레임워크(FastAPI, SQLAlchemy) import 금지. `core/domain`의 베이스(`Entity`, `ValueObject`, 예외 카테고리)만 상속한다. HTTP 상태 코드 등 표현 방식도 모른다.
- **api는 application까지만 의존한다.** 라우터가 repository를 직접 호출하지 않는다.
- **application은 concrete infrastructure에 의존하지 않는다.** command/query use case는 domain과 application port contract, `app.core.application`의 공용 primitive까지만 안다.
- 모듈 루트의 `dependencies.py`가 계층 간 wiring(FastAPI `Depends` 체인)을 담당한다. 테스트는 모듈 conftest(`app/modules/examples/tests/conftest.py`)의 `override_example_user_service` fixture로 서비스 전체를 대체한다 (teardown에서 자동 clear).
- 모듈 간 런타임 연결이 필요하면 각 모듈의 `dependencies.py`에서만 조립한다. application/domain에는 다른 BC의 infrastructure, provider SDK, DB session, concrete adapter import가 들어가면 안 된다.
- Cross-BC consistency가 필요한 같은 DB workflow는 `dependencies.py`에서 request-scoped session/transaction을 만들고 관련 repository/use case가 같은 session을 공유하게 한다. 별도 `app/composition` 패키지는 두지 않는다.
- Production 모듈의 application command flow는 `application/commands/<business_task>/{command.py,result.py?,use_case.py}`로 노출한다. UseCase 클래스 이름은 migrated flow에서 `*CommandUseCase`를 사용하고, application DTO 파일은 `schemas.py`가 아니라 `command.py`와 `result.py`처럼 역할명으로 둔다.
- Production 모듈의 내부 side-effect-free read flow는 `application/queries/<read_task>/{query.py,result.py?,use_case.py}`로 노출한다. UseCase 클래스 이름은 migrated flow에서 `*QueryUseCase`를 사용하고, application DTO 파일은 `query.py`와 `result.py`처럼 역할명으로 둔다.
- `read_models`는 public optimized read API/read model surface가 필요하고 그 최적화/보안 요구가 문서화된 경우에만 사용한다. 내부 조회 흐름에 `read_models`를 요구하지 않는다.
- API 전송 스키마 파일은 `api/schemas.py`에 둘 수 있다. 이 규칙은 application DTO 파일명에 대한 정책이다.
- command bus/query bus는 이후 명시 승인 없이는 두지 않는다. event sourcing, outbox, external message bus, Kafka/RabbitMQ/Celery, separate read DB, read-store, projection worker, materialized view도 현재 아키텍처 범위 밖이다.
- 도메인 이벤트는 `DomainEvent`와 `EventDispatcher`를 통한 same-process side effect까지만 의미한다. retry/replay, broker, cross-process delivery, durability contract는 이 아키텍처의 기본 이벤트 의미가 아니다.

## 요청 흐름

```
HTTP 요청
  │
  ▼
APIRouter (app/modules/examples/api/router.py)
  │  요청 형태 검증 (CreateExampleUserRequest — 타입/필수 필드만, 규칙 검증 없음)
  ▼
Dependency 체인 (app/modules/examples/dependencies.py)
  │  get_example_user_repository() → get_example_user_service() → ExampleUserServiceDep
  ▼
ExampleUserService (application/service.py)
  │  도메인 로직 조립: ExampleUser.create() 호출 → 영속화. 부재 시 ExampleUserNotFoundError 발생
  ▼
ExampleUser.create() (domain/model.py)
  │  생성 규칙 실행 — Notification이 값 객체(Nickname/Email/Password) 검증 실패를 집계해 ValidationError 발생
  ▼
ExampleUserRepository (infrastructure/repository.py)
  │  엔티티 영속화(save) / 조회(get)
  ▼
라우터가 엔티티 → ExampleUserResponse 변환
  ▼
CommonResponse(success=True, status=..., data=...) envelope로 응답
```

성공 응답 예시 (`POST /api/v1/examples`, 201):

```json
{
  "success": true,
  "status": 201,
  "data": {
    "id": "….uuid…",
    "nickname": "created-user",
    "email": "created@test.com"
  }
}
```

## 에러 처리 흐름

모든 실패는 `app/core/http/exception_handlers.py`의 전역 핸들러를 거쳐 동일한 실패 envelope(`CommonResponse[ApiErrorData]`)로 변환된다. 핸들러 등록은 `create_app()` 내 `_register_exception_handlers()`에서 수행한다.

도메인 예외는 HTTP를 모른다 — **의미 카테고리 → 상태 코드 매핑은 핸들러 등록이 전담**하며, FastAPI의 "subclass 핸들러 우선" 규칙 덕분에 모듈 예외는 자기 카테고리의 핸들러에 자동 흡수된다.

```
ValidationError (도메인 검증 집계) ──► handle_domain_validation_error ──► 422
NotFoundError (대상 부재) ─────────► handle_not_found_error ──────────► 404
DomainError (미분류 안전망) ────────► handle_domain_error ─────────────► 400
RequestValidationError ───────────► handle_request_validation_error ─► 422
HTTPException (Starlette) ────────► handle_http_exception ───────────► 예외의 status_code
Exception (catch-all) ────────────► handle_unexpected_error ─────────► 500 + 로깅
                                      (모두 CommonResponse(success=false, status, data=ApiErrorData))
```

- `ValidationError`: **사용자 대면 검증 규칙(이메일 형식, 비밀번호 길이 등)은 각 BC의 값 객체가 생성 시점에 검증하고, 필드별 메시지도 규칙을 소유한 값 객체가 직접 정의한다.** `message`는 대표 요약("입력값이 올바르지 않습니다."), 필드별 메시지는 `errors` 배열 전담. 엔티티 `create()` 팩토리가 `Notification`(`app/core/domain/validation.py`, Fowler의 Notification 패턴)으로 모든 실패를 집계해 한 번에 던지므로 다중 필드 실패가 전부 `errors`에 담긴다.
- `NotFoundError`: 모듈 예외(예: `ExampleUserNotFoundError(example_user_id)`)가 상속하고 message + 발생 맥락을 보유한다.
- `RequestValidationError`: BC에 도달할 수 없는 깨진 요청(필수 필드 누락, 타입 불일치)만 담당한다. 상태 코드는 FastAPI 기본인 **422**를 유지하되 본문을 실패 envelope으로 교체하고, `FieldError.from_pydantic_error()`가 loc 접두사(body/query/...)를 제거해 `errors` 배열을 만든다. 이 경로의 message는 고정 요약("요청 값이 올바르지 않습니다.")이다.
- `HTTPException`: detail 문자열을 message로 사용 (404 라우트 미존재 등).
- `Exception`: 처리되지 않은 예외도 envelope 일관성을 유지하며 내부 정보 없이 500으로 응답하고, 전체 스택을 로깅한다.

실패 응답 예시 (도메인 검증 실패, 422):

```json
{
  "success": false,
  "status": 422,
  "data": {
    "timestamp": "2026-06-11T00:00:00",
    "message": "입력값이 올바르지 않습니다.",
    "path": "/api/v1/examples",
    "errors": [
      {"field": "email", "message": "이메일 형식이 올바르지 않습니다."}
    ]
  }
}
```

## 설계 결정 기록

### 앱 팩토리 + lifespan

`create_app(settings)`가 FastAPI 인스턴스를 만들고, DB 엔진/세션 팩토리는 lifespan에서 생성해 `app.state.engine` / `app.state.session_factory`에 둔다. import 시점 부작용(전역 엔진 생성)이 없어 테스트에서 `Settings`를 주입한 독립 앱을 만들 수 있고, 종료 시 `engine.dispose()`가 보장된다. `tests/test_app.py::test_database_state_is_created_by_lifespan_not_import`가 이 계약을 검증한다.

### CommonResponse envelope

모든 응답이 `{success, status, data}` 형태를 따른다. 클라이언트는 HTTP 상태와 무관하게 단일 파싱 경로를 가지며, 실패 시 `data`가 `ApiErrorData`(timestamp/message/path/errors)로 고정된다.

### pydantic-settings 기반 설정

`Settings(BaseSettings)`가 `.env` 파일과 환경변수에서 값을 읽는다 (`app_env`: local/test/dev/staging/prod). `get_settings()`는 `lru_cache`로 캐시되지만, `create_app()`은 인자로 받은 `Settings`를 우선 사용하므로 테스트에서 캐시를 우회할 수 있다.

### SQLAlchemy naming convention

`app/core/db/base.py`의 `Base.metadata`에 ix/uq/ck/fk/pk 명명 규칙을 고정한다. Alembic autogenerate 시 제약 이름이 결정적으로 생성되어, 이름 없는 제약의 drop 불가 문제를 예방한다.

### expire_on_commit=False + pool_pre_ping

- `expire_on_commit=False`: commit 후 속성 접근 시 암묵적 refresh(추가 I/O, async 컨텍스트 밖 접근 오류)를 방지한다.
- `pool_pre_ping=True`: 풀에서 꺼낸 커넥션의 유효성을 사전 확인해 끊긴 커넥션으로 인한 실패를 막는다.

### 검증 실패는 422로 통일

요청 형식 오류(`RequestValidationError`)와 도메인 필드 검증 실패(`ValidationError`) 모두 FastAPI/HTTP 표준(RFC 9110)에 맞춰 **422**로 응답한다. 상태 코드가 기본값과 같으므로 별도 OpenAPI 보정 없이, 라우터의 `responses=` 선언으로 422 본문 스키마만 기본 `HTTPValidationError`에서 실패 envelope(`CommonResponse[ApiErrorData]`)으로 교체한다 (`test_openapi_documents_actual_error_responses`가 이 계약을 고정).

## 알려진 공백 / 로드맵

코드를 기준으로 한 현재 상태이며, 의도적으로 미뤄둔 항목들이다.

- **요청 단위 DB 세션 dependency 미구현**: `app.state.session_factory`는 lifespan에서 만들어지지만 이를 소비하는 `Depends`가 없다. 현재 어떤 요청 경로도 DB에 접근하지 않는다.
- **examples repository는 in-memory placeholder**: `ExampleUserRepository`가 ClassVar dict에 저장한다. SQLAlchemy 기반 구현으로 교체 예정. ORM 모델/마이그레이션도 아직 없다 (alembic 골격만 존재).
- **`/ready` 미구현**: `/health`는 liveness 수준의 정적 응답만 한다. DB 등 의존성 점검을 포함한 readiness probe가 필요하다 (`test_ready_endpoint_is_not_exposed_until_it_checks_dependencies`가 현재 404임을 고정).
- **로깅/CORS 미설정**: 구조화 로깅, CORS 미들웨어가 없다.
- **이메일 검증이 단순 휴리스틱**: `Email` 값 객체가 `@`/`.` 존재만 확인한다. 정교한 검증이 필요해지면 `Email.validate()` 내부에서 email-validator 라이브러리 활용 검토.
- **pyright strict 전환 예정**: 현재 `typeCheckingMode = "standard"`. 커버리지가 안정되면 strict로 올린다.

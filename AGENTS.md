# AGENTS.md

Receipt Keeper backend API — FastAPI + SQLAlchemy 2.0(async) + PostgreSQL + Alembic, Python 3.12, 패키지 관리는 uv.

## 핵심 명령어

Makefile 타겟을 우선 사용한다. 원시 uv 명령은 보조 수단이다.

| 명령 | 동작 | 원시 명령 |
|---|---|---|
| `make install` | 의존성 설치 + pre-commit 훅 등록 | `uv sync --all-groups && uv run pre-commit install` |
| `make lint` | 린트 검사 | `uv run ruff check` |
| `make format` | 코드 포맷팅 | `uv run ruff format` |
| `make typecheck` | 타입 검사 | `uv run pyright` |
| `make test` | 테스트 실행 (커버리지 포함) | `uv run pytest` |
| `make check` | lint + format --check + typecheck + test 순차 실행 | — |

- 의존성 추가: `uv add <pkg>`, dev 의존성은 `uv add --dev <pkg>`. pyproject.toml을 직접 편집하지 말 것.
- 로컬 서버: `uv run fastapi dev app/main.py`
- 마이그레이션: `uv run alembic revision --autogenerate -m "..."` / `uv run alembic upgrade head`

## 패키지 구조

```
conftest.py                    # 공용 client fixture (전체 테스트에서 사용)
tests/                         # 앱 수준 통합 테스트만 (health, lifespan, settings, OpenAPI)
app/
├── core/                      # 공유 인프라 (도메인 모듈이 의존하는 공통 계층)
│   ├── config/                # Settings (pydantic-settings, .env 로드)
│   ├── db/                    # Base (naming convention 적용 메타데이터), 엔진/세션 팩토리
│   ├── domain/                # Entity / ValueObject 베이스, 예외 카테고리(DomainError 계층), Notification
│   ├── http/                  # CommonResponse 봉투, ApiErrorData, 전역 예외 핸들러
│   ├── observability/         # /health 라우터
│   └── tests/                 # core 베이스 계약 테스트
├── modules/<도메인>/           # 도메인별 수직 슬라이스 모듈
│   ├── api/                   # router.py (엔드포인트 + 에러 응답 OpenAPI 선언), schemas.py (요청/응답 모델)
│   ├── application/           # service.py (유스케이스 오케스트레이션)
│   ├── domain/                # model.py (엔티티), value_objects.py (값 객체), exceptions.py (도메인 예외)
│   ├── infrastructure/        # repository.py (영속성 구현)
│   ├── tests/                 # 모듈 소유 테스트 + 모듈 전용 fixture (conftest.py)
│   └── dependencies.py        # FastAPI DI 와이어링 (repository → service)
└── main.py                    # create_app() 팩토리, 라우터/예외 핸들러 등록, lifespan에서 DB 엔진 생성
```

### 계층 의존 방향 (모듈 내부)

```
api → application → domain ← infrastructure
```

- **api**: HTTP 입출력 변환만 담당. 요청 스키마를 받아 service를 호출하고 `CommonResponse`로 감싼다. 비즈니스 로직 금지. 스키마는 전송 형태(타입/필수 여부)만 정의하고 검증 규칙을 넣지 않는다.
- **application**: 유스케이스 단위 오케스트레이션. 도메인 로직(엔티티 팩토리·값 객체)을 조립하고 repository를 호출만 한다. 검증·생성 규칙을 직접 구현하지 말 것 — domain에 둔다.
- **domain**: 순수 엔티티(`model.py` — 생성 규칙은 `create()` 팩토리), 값 객체(`value_objects.py` — `ValueObject` 상속, 생성 시 자체 검증하며 자기 메시지 소유), 도메인 예외(`exceptions.py`). core 외의 다른 계층을 import하지 않는다.
- **infrastructure**: repository 등 영속성 구현. 엔티티를 받아 저장/조회만 한다.
- 모듈 간 직접 import 금지. 공유가 필요하면 `app/core`로 올린다.

## 컨벤션

- **응답 봉투**: 모든 API 응답은 `CommonResponse[DataT]` (`app/core/http/responses.py`) — `{"success": bool, "status": int, "data": ...}`. 성공 응답은 엔드포인트에서 직접 감싸고, 실패 응답은 전역 핸들러가 `ApiErrorData`(timestamp, message, path, errors)로 만든다.
- **검증 실패는 422**: 요청 형식 오류(`RequestValidationError`)와 도메인 필드 검증 실패(`ValidationError`) 모두 422로 응답한다. `data.message`는 응답 전체의 대표 요약이고, 필드별 메시지는 `data.errors[]`가 전담한다 — 특정 필드의 메시지를 `message`에 올리지 말 것.
- **도메인 에러는 의미만 표현한다 (HTTP 무지)**: 모듈 예외는 의미 카테고리(`ValidationError`, `NotFoundError` — `app/core/domain/exceptions.py`)를 상속하고, message + 발생 맥락(예: `ExampleUserNotFoundError(example_user_id)`)만 가진다. **status_code를 들고 다니지 말 것** — HTTP 매핑은 `app/main.py`의 핸들러 등록(카테고리→상태코드, subclass 우선)이 전담한다. 엔드포인트에서 try/except로 잡지 말 것. 새 카테고리(예: Conflict→409)는 첫 유스케이스가 생길 때 core에 추가한다.
- **필드 검증 메시지는 값 객체가 소유**: 규칙 상수와 위반 메시지를 값 객체의 `validate()` 안에 함께 둔다. 값 객체는 `ValidationError([ErrorDetail(field=..., message=...)])`를 던지고, 엔티티 `create()` 팩토리는 `Notification`(`app/core/domain/validation.py`)으로 모든 실패를 집계해 한 번에 던진다 (다중 필드 실패 시 `errors[]`에 전부 담김). 모듈에 집계 메커니즘 코드를 작성하지 말 것.
- **에러 응답 OpenAPI 문서화**: 라우터에 `responses={...}`로 422/404 등 실패 envelope 스키마(`CommonResponse[ApiErrorData]`)를 선언해 `/docs`가 실제 응답과 일치하게 유지한다.
- **에러 메시지**: 사용자 대면 메시지(도메인 예외, 검증 메시지)는 한국어로 작성한다.
- **async 전용**: 모든 엔드포인트/서비스/repository 메서드는 `async def`. sync 엔드포인트와 이벤트 루프를 막는 블로킹 호출(동기 DB 드라이버, `time.sleep`, 동기 HTTP 클라이언트 등) 금지.
- **타입 힌트 필수**: 모든 함수 시그니처에 인자/반환 타입을 명시한다 (pyright standard 통과 필수, strict 전환은 로드맵).
- **DB 제약조건 이름**: `Base` (`app/core/db/base.py`)의 naming convention이 자동 적용된다. ORM 모델은 반드시 이 `Base`를 상속할 것 (Alembic autogenerate가 일관된 제약조건 이름에 의존).
- **설정**: 환경 변수는 `Settings` (`app/core/config/settings.py`)에 필드로 추가. 코드에서 `os.environ` 직접 접근 금지.
- **앱 상태**: DB 엔진/세션 팩토리는 import 시점이 아니라 lifespan에서 생성되어 `app.state`에 저장된다. 이 패턴을 유지할 것.

## 새 모듈 추가 절차

`app/modules/examples`를 템플릿으로 삼는다.

1. `app/modules/<이름>/` 아래에 `api/`, `application/`, `domain/`, `infrastructure/`, `tests/`, `dependencies.py` 생성.
2. `domain/model.py`: `Entity[IdT]` 상속 엔티티 + 생성 규칙을 담은 `create()` 팩토리 (`Notification`으로 검증 집계). `domain/value_objects.py`: `ValueObject[ValueT]` 상속 값 객체 (규칙·메시지 소유, `ValidationError` 발생). `domain/exceptions.py`: 의미 카테고리(`NotFoundError` 등) 상속 예외 (맥락 파라미터 수신, status_code 없음).
3. `infrastructure/repository.py`: 영속성 구현 — 엔티티를 받아 저장/조회만 한다 (실제 모듈은 `app.state.session_factory`의 `AsyncSession` 사용).
4. `application/service.py`: repository를 생성자 주입받는 서비스 클래스.
5. `api/schemas.py`: `AppBaseModel` 상속 요청/응답 모델. `api/router.py`: `APIRouter(prefix="/<이름>", responses={422/404 envelope 선언})` + `CommonResponse` 반환.
6. `dependencies.py`: `Depends` 체인으로 service를 조립하고 `Annotated` 타입 별칭(`XxxServiceDep`) 노출.
7. `app/main.py`의 `create_app()`에서 `app.include_router(<router>, prefix=resolved_settings.api_prefix)` 등록.
8. `tests/`(모듈 내부)에 envelope 계약 테스트 + 모듈 전용 override fixture(conftest.py) 추가, ORM 모델 추가 시 Alembic 마이그레이션 생성 후 `make check` 통과 확인.

## 테스트 규칙

- **배치**: 모듈 테스트는 `app/modules/<이름>/tests/`, core 베이스 계약 테스트는 `app/core/tests/`, 앱 수준 통합 테스트(health, lifespan, settings)는 최상위 `tests/`. 모듈 내 tests/는 커버리지 측정에서 제외된다 (`omit = ["*/tests/*"]`).
- `asyncio_mode = "auto"` — async 테스트 함수에 데코레이터 불필요. 그냥 `async def test_...`로 작성.
- HTTP 호출은 루트 `conftest.py`의 `client` fixture(httpx `ASGITransport` — 실서버/실DB 불필요), 서비스 교체는 모듈 conftest의 `override_example_user_service` fixture를 사용한다 (teardown에서 override 자동 clear).
- 성공/실패 모두 envelope 계약(`success`, `status`, `data` 구조)을 검증한다.
- 실행: `make test`. ruff S 규칙의 예외는 tests 디렉토리 한정(`**/tests/**`) — `assert`(S101)와 더미 비밀번호(S106)만 허용된다.

## 주의사항

- **`app/modules/examples`는 참조용 예시 모듈이다.** 특히 in-memory `ExampleUserRepository`(ClassVar dict)는 데모용일 뿐 실제 패턴이 아니다 — 실제 모듈은 SQLAlchemy `AsyncSession` 기반 repository를 구현해야 한다.
- `README.md` 본문 서술은 사용자가 관리한다 — 코드와의 사실 불일치 수정 외에는 건드리지 말 것. `docs/`, `.omc/`, `.omx` 디렉토리도 건드리지 말 것.
- 커밋 전 `make check`가 통과해야 한다. pre-commit 훅(ruff check --fix, ruff-format 등)이 설치되어 있다.

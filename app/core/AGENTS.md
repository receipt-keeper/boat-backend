# CORE KNOWLEDGE BASE

## OVERVIEW

공유 플랫폼 계층이다. domain module은 `app.core`를 import할 수 있지만, `app.core`는 domain module을 import하면 안 된다.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Settings | `config/settings.py` | Pydantic Settings와 cached `get_settings()`. |
| Request settings | `config/dependencies.py` | `request.app.state.settings`를 읽는다. |
| SQLAlchemy base | `db/base.py` | Alembic autogenerate용 naming convention. |
| Engine/session builders | `db/session.py` | builder만 둔다. lifecycle은 `app/main.py`. |
| Unit of work | `application/unit_of_work.py`, `db/unit_of_work.py` | port는 application, SQLAlchemy 구현은 db. |
| Domain bases | `domain/` | Entity, value object, event, exceptions, validation aggregation. |
| Security principal | `security/principal.py` | `AuthenticatedPrincipal`의 SSOT. |
| Response envelope | `http/responses.py` | `CommonResponse`, `ApiErrorData`, `FieldError`. |
| Exception handlers | `http/exception_handlers.py` | error envelope 변환과 logging. |
| Event dispatch | `application/event_dispatcher.py` | same-process dispatch만 의미한다. durability contract 없음. |
| Health | `observability/health.py` | liveness endpoint only. |
| Core contracts | `tests/` | core behavior tests는 core 옆에 둔다. |

## CONVENTIONS

- 이 계층은 domain-neutral이어야 한다. 이름은 여러 module에서 자연스럽게 재사용 가능해야 한다.
- 환경 변수는 `Settings` field로 추가한다. caller는 app state 또는 DI로 settings를 받는다.
- core 밖 ORM model은 `Base`를 상속한다. 별도 declarative base를 만들지 않는다.
- Domain exception class는 의미만 표현한다. HTTP mapping은 `http/exception_handlers.py`와 `app/main.py`가 담당한다.
- `ValidationError`는 집계된 `ErrorDetail`을 담는다. 여러 field 실패를 모을 때 `Notification`을 쓴다.
- `FieldError.from_pydantic_error()`가 request validation field normalization을 소유한다.
- `AuthenticatedPrincipal`은 core security가 소유한다. auth application package로 되돌리지 않는다.
- `EventDispatcher`는 in-process utility다. outbox, retry, replay, broker 의미를 암시하지 않는다.

## ANTI-PATTERNS

- core에서 `app.modules.*`를 import하지 않는다.
- module-specific value, table, provider, router를 core에 넣지 않는다.
- core domain primitive가 FastAPI, SQLAlchemy, HTTP status code를 알게 만들지 않는다.
- engine/session lifecycle을 `db/session.py`로 옮기지 않는다. app lifespan에 둔다.
- 여러 module에서 쓸 수도 있다는 이유만으로 security/provider helper를 core에 먼저 넣지 않는다.

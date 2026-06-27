# APP KNOWLEDGE BASE

## OVERVIEW

FastAPI source tree. `app/main.py`가 runtime state, dependency override, router, exception handler를 조립한다. child package가 platform code와 domain module을 소유한다.

## STRUCTURE

```text
app/
├── main.py       # create_app(), lifespan, dependency overrides, router/handler registration
├── core/         # shared platform primitives
└── modules/      # vertical domain modules
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| App factory | `main.py` | `create_app(settings)`가 진입점이다. |
| DB state | `main.py` | lifespan에서 `engine`과 `session_factory`를 만들어 `app.state`에 둔다. |
| Router registration | `main.py` | business router는 `resolved_settings.api_prefix`를 쓴다. health는 API prefix 밖이다. |
| Protected routers | `main.py` | `users`, `files`, `receipts`, `credits`, `notifications`, `usage`는 include 시점에 `authenticate_current_principal`가 붙는다. |
| Public auth/OCR routers | `main.py` | `auth`, `ocr`는 global bearer dependency 없이 include한다. endpoint-level behavior는 각 모듈 소유. |
| File delete guard override | `main.py` | files의 `get_file_reference_guard`를 users의 `get_profile_image_file_reference_guard`로 override한다. |
| Exception mapping | `main.py` | 구체 handler를 generic `DomainError`, catch-all보다 먼저 등록한다. |
| Shared primitives | `core/` | module은 core에 의존할 수 있다. |
| Business slices | `modules/` | cross-module wiring은 module `dependencies.py`에 둔다. |

## CONVENTIONS

- `app/main.py`가 composition root다. router, handler, settings, DB builder, dependency override endpoint만 명시적으로 import한다.
- DB engine/session factory 생성은 import time이 아니라 lifespan에 둔다.
- composition이 만든 runtime object만 `app.state`에 저장한다.
- HTTP endpoint behavior는 router module이 소유한다. `app/main.py`는 router include와 app-level dependency만 담당한다.
- Business API는 기본적으로 `CommonResponse`를 반환한다. `/health`는 운영 probe라 envelope 밖에 둔다.
- protected module router를 추가하면 문서화된 public contract가 없는 한 `prefix=resolved_settings.api_prefix`와 bearer dependency를 같이 붙인다.
- domain error category를 추가할 때는 core/domain category를 먼저 만들고, 여기서 HTTP mapping을 등록한다.
- cross-module dependency override가 필요하면 override target과 replacement를 모두 module-owned로 유지하고 관련 child AGENTS에 기록한다.

## ANTI-PATTERNS

- `app/composition` package를 만들지 않는다.
- import time에 global DB engine, session factory, SDK client, settings-dependent runtime object를 만들지 않는다.
- module-specific dependency graph를 `main.py`에 넣지 않는다. `app/modules/<module>/dependencies.py`에 둔다.
- `app/core`가 `app/modules`에 의존하게 만들지 않는다.
- users endpoint를 auth router에 mount하거나 files endpoint를 users router에 mount하지 않는다.

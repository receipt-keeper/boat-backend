# AUTH MODULE KNOWLEDGE BASE

## OVERVIEW

Auth는 외부 identity 검증, backend-issued access JWT, opaque refresh token, bearer principal 복원을 소유한다.

## STRUCTURE

```text
auth/
├── api/              # /auth routes, transport schemas, auth-specific exception handlers, security deps
├── application/      # commands, queries, provider-neutral ports
├── domain/           # credential, external identity, refresh token entities/value objects
├── infrastructure/   # Firebase, JWT, opaque refresh token, SQLAlchemy adapters
├── dependencies.py   # shared transaction session and cross-module users provisioning wiring
└── tests/            # API, service, dependency, security, architecture guards
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Routes | `api/router.py` | `POST /login`, `POST /refresh`, `POST /logout`. users endpoint를 여기 mount하지 않는다. |
| Principal deps | `api/security.py` | Bearer extraction과 role guard. 복원된 principal model은 core-owned. |
| Auth errors | `api/exception_handlers.py` | 401/403 failure envelope. |
| Login command | `application/commands/login/use_case.py` | identity 검증, user resolve/provision, credential 생성, token 발급. |
| Refresh command | `application/commands/refresh/use_case.py` | refresh token rotate와 새 access token pair 발급. |
| Logout command | `application/commands/logout/use_case.py` | 제출된 refresh token revoke. |
| Withdraw command | `application/commands/withdraw/use_case.py` | auth credential 삭제와 user deletion/cleanup 요청. public route는 users BC의 `DELETE /api/v1/users/me`. |
| Current principal query | `application/queries/current_principal/use_case.py` | side effect 없이 bearer principal을 복원하고 active credential을 검증한다. |
| Token contracts | `application/ports/token_issuer.py` | provider-neutral access/refresh token ports. |
| Principal model | `app/core/security/principal.py` | `AuthenticatedPrincipal`의 SSOT. |
| Runtime wiring | `dependencies.py` | credential repository와 user provisioning이 하나의 transaction session을 공유한다. |
| Persistence | `infrastructure/persistence/` | ORM, mapper, credential repository, login synchronizer. |
| Provider adapter | `infrastructure/identity_providers/firebase.py` | Firebase SDK 격리 지점. |
| Regression guard | `tests/test_architecture.py` | file layout, forbidden import, router surface, token port contract. |

## CONVENTIONS

- Auth application command package는 `application/commands/<business_task>/` 아래에 둔다.
- Auth internal side-effect-free read flow는 `application/queries/<read_task>/` 아래에 둔다.
- Application DTO file은 `command.py`, `query.py`, `result.py`처럼 역할명으로 둔다. API transport schema는 `api/schemas.py` 가능.
- Migrated flow use case는 `*CommandUseCase` 또는 `*QueryUseCase`를 쓴다.
- `read_models`는 public optimized read API/read model surface용이다. 내부 auth query에는 요구하지 않는다.
- Auth는 기본 application DB를 쓴다. 별도 read DB/read-store/projection worker/materialized view는 명시 승인 없이는 금지다.
- Command bus/query bus는 명시 승인 없이는 금지다.
- 도메인 이벤트는 실제 command 상태 변경에서만 발행하고, 발행 경로는 core-owned transactional outbox(`app.core.db.outbox`) 경유만 허용한다. synchronous in-process handler는 실제 소비 요구가 생길 때 main.py 조립 지점에서 등록한다.
- Application code는 port와 domain object에만 의존한다. Firebase, JWT, SQLAlchemy, auth infrastructure, users infrastructure import 금지.
- Token port는 provider-neutral이어야 한다. contract 이름에 JWT-specific naming을 넣지 않는다.
- `dependencies.py`만 auth와 users provisioning을 연결한다.
- `get_auth_transaction_session()`은 성공 시 commit, `BaseException` 발생 시 rollback한다. signup/login wiring 변경 시 보존한다.
- Firebase verification은 SDK call이 sync라 `asyncio.to_thread()`를 통해 실행한다.
- Auth domain message는 한글이고 domain exception은 HTTP를 모른다.
- Access token은 backend-issued JWT다. Refresh token은 opaque이고 hash만 저장한다.
- Command result는 HTTP `token_type`을 소유하지 않는다. `token_type`은 API response shaping 영역이다.

## ANTI-PATTERNS

- `/logout-all`을 추가하지 않는다.
- scope가 명시적으로 다시 열리기 전까지 Firebase custom-token issuance나 direct Apple OIDC verification을 추가하지 않는다.
- users public API belongs to the users BC.
- Do not mount users endpoints in the auth router.
- `app.modules.users.infrastructure`를 auth에서 import하지 않는다.
- auth/users wiring을 위해 `app/composition`을 만들지 않는다.
- `tests/test_architecture.py`가 막는 old file name을 되살리지 않는다.
- `AuthenticatedPrincipal`을 auth application package로 되돌리지 않는다.
- business decision을 Firebase, JWT, SQLAlchemy adapter로 옮기지 않는다.
- NoOpPushCleanup cannot satisfy PRD-complete withdrawal; it must not be used to claim PRD-complete withdrawal cleanup, and missing BC cleanup must remain unclaimed until the real owning BC and cleanup contract exist.
- event sourcing, durable event store, retry, replay, external message bus, Kafka/RabbitMQ/Celery, cross-process delivery를 auth에 도입하지 않는다. 유일한 예외는 core-owned transactional outbox(`app.core.db.outbox`) 경유 발행이며, auth가 자체 outbox/durability 구현을 소유하는 것은 여전히 금지다.
- 사용처 없는 추측성 이벤트 타입을 추가하지 않는다. Auth event(현재: `UserCredentialCreated`, `AccountWithdrawn`)는 실제 command 상태 변경에서 발행되어야 하며, 소비자(handler)는 단계적으로 도입한다.

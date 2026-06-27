# MODULES KNOWLEDGE BASE

## OVERVIEW

Domain module은 vertical slice다. 각 module이 API, application command/query use case, domain model, infrastructure adapter, tests, FastAPI DI wiring을 소유한다.

## STRUCTURE

```text
modules/
├── auth/            # external identity -> backend access/refresh tokens
├── users/           # mypage profile API, profile image, provisioning/deletion contracts
├── files/           # upload/metadata/content/delete, storage adapter, reference guard
├── receipts/        # receipt aggregate and receipt APIs
├── ocr/             # receipt image OCR boundary
├── credits/         # user-owned usage allowance balance
├── usage/           # feature usage availability/history
├── notifications/   # notification list/settings contract
└── assets/          # placeholder only; no public router today
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| HTTP endpoints | `<module>/api/` | Router와 Pydantic transport schema. |
| Commands | `<module>/application/commands/<business_task>/` | 변경 flow. `command.py`, optional `result.py`, `use_case.py`. |
| Queries | `<module>/application/queries/<read_task>/` | 내부 side-effect-free read flow. `query.py`, optional `result.py`, `use_case.py`. |
| Read models | `<module>/application/read_models/` | public optimized read API/read model surface 전용. 내부 query에 요구하지 않는다. |
| Domain rules | `<module>/domain/` | Entity, value object, module exception. |
| Persistence/providers | `<module>/infrastructure/` | concrete adapter만 둔다. |
| Runtime DI | `<module>/dependencies.py` | repository/storage/provider에서 command/query use case로 wiring한다. |
| Tests | `<module>/tests/` | module-owned API, service, fixture, architecture tests. |
| Cross-BC app contracts | `tests/test_bc_domain_contracts.py`, `tests/test_bc_mock_contracts.py` | repo-level public contract checks. |
| DB session ownership | `tests/test_db_session_architecture.py` | module은 core DB session/unit-of-work를 쓴다. module-local session scope 금지. |

## CONVENTIONS

- 내부 방향은 `api -> application -> domain <- infrastructure`다.
- `api`는 HTTP input/output 변환과 envelope response만 담당한다. business logic 금지.
- `application`은 command/query use case로 조립한다. domain과 ports에는 의존할 수 있지만 concrete adapter에는 의존하지 않는다.
- Production command flow는 `application/commands/<business_task>/{command.py,result.py?,use_case.py}`를 쓴다.
- Production internal read flow는 `application/queries/<read_task>/{query.py,result.py?,use_case.py}`를 쓴다.
- Application DTO file은 `command.py`, `query.py`, `result.py`처럼 역할명으로 둔다. API transport schema는 `api/schemas.py` 가능.
- migrated command/query flow use case는 generic `*UseCase`가 아니라 `*CommandUseCase` 또는 `*QueryUseCase`를 쓴다.
- command bus/query bus는 명시 승인 전까지 추가하지 않는다.
- `domain`은 pure layer다. core domain base/category만 사용할 수 있다.
- `infrastructure`는 저장, mapping, provider 호출을 맡는다. business rule을 소유하지 않는다.
- Cross-module runtime composition은 module `dependencies.py`에서만 한다.
- Cross-module reference는 UUID value와 application contract를 쓴다. cross-BC ORM FK나 infrastructure import를 쓰지 않는다.
- 중요한 boundary는 module `tests/test_architecture.py`로 고정한다.
- module이 ORM model을 추가하면 Alembic migration을 추가하고 same-BC FK만 둔다.
- mock-backed app contract module(`credits`, `usage`, `notifications`)도 API schema와 한글 OpenAPI 문구를 각자 소유한다. shared mock package로 합치지 않는다.

## ANTI-PATTERNS

- 다른 module의 `infrastructure`를 import하지 않는다.
- FastAPI `Depends` chain을 application/domain layer에 넣지 않는다.
- value object가 소유해야 할 rule을 request schema validation으로 옮기지 않는다.
- 실제 use case 없이 speculative module root나 shared abstraction을 만들지 않는다.
- event sourcing, outbox, external message bus, Kafka/RabbitMQ/Celery, separate read DB, read-store, projection worker, materialized view는 명시 승인 전까지 도입하지 않는다.
- migrated production module에서 `application/service.py`, `application/schemas.py`, `infrastructure/repository.py` 같은 old flat file을 쓰지 않는다.

# MODULES KNOWLEDGE BASE

## OVERVIEW

Domain modules are vertical slices. Each module owns its API, application command/query use cases, domain model, infrastructure adapters, tests, and FastAPI DI wiring.

## STRUCTURE

```text
modules/
├── auth/            # Firebase identity -> backend access/refresh tokens
├── users/           # user profile and provisioning contract
├── files/           # file metadata/content boundary
├── ocr/             # OCR analysis boundary
├── receipts/        # receipt domain
├── assets/          # registered asset domain
├── credits/         # user-owned usage allowance balance
├── usage/           # usage event history
└── notifications/   # user notification delivery/settings
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| HTTP endpoints | `<module>/api/` | Router + Pydantic transport schemas. |
| Commands | `<module>/application/commands/<business_task>/` | Mutating application flows with `command.py`, optional `result.py`, and `use_case.py`. |
| Queries | `<module>/application/queries/<read_task>/` | Internal side-effect-free read flows with `query.py`, optional `result.py`, and `use_case.py`. |
| Read models | `<module>/application/read_models/` | Reserved for public optimized read API/read model surfaces; do not require this for internal queries. |
| Domain rules | `<module>/domain/` | Entities, value objects, module exceptions. |
| Persistence/providers | `<module>/infrastructure/` | Concrete adapters only. |
| Runtime DI | `<module>/dependencies.py` | Repository -> command/query use case wiring. |
| Tests | `<module>/tests/` | Module-owned API, service, fixture, architecture tests. |

## CONVENTIONS

- Internal direction remains `api -> application -> domain <- infrastructure`.
- `api` converts HTTP input/output and returns envelope responses. No business logic.
- `application` orchestrates through command/query use cases. It may depend on domain and ports, not concrete adapters.
- Production command flows use `application/commands/<business_task>/{command.py,result.py?,use_case.py}`.
- Production internal read flows use `application/queries/<read_task>/{query.py,result.py?,use_case.py}`.
- Application DTO files are named by role (`command.py`, `query.py`, `result.py`), not generic `schemas.py`. API transport schema may stay in `api/schemas.py`.
- Migrated command/query flow use cases use `*CommandUseCase` or `*QueryUseCase`, not generic `*UseCase`.
- Do not add command bus/query bus unless explicitly approved later.
- `domain` is pure and may use only core domain bases/categories.
- `infrastructure` stores, maps, or calls providers. It does not own business rules.
- Cross-module runtime composition happens only through module `dependencies.py`.
- Module tests should include envelope assertions for endpoints and architecture guards for import boundaries when a boundary is important.
- If a module adds ORM models, add an Alembic migration and keep same-BC FKs only.

## ANTI-PATTERNS

- Do not import another module's `infrastructure`.
- Do not put FastAPI `Depends` chains inside application or domain layers.
- Do not put request-schema validation where a value object should own the rule.
- Do not introduce speculative module roots or shared abstractions before a real use case exists.
- Do not introduce event sourcing, outbox, external message bus, Kafka/RabbitMQ/Celery, separate read DB, read-store, projection worker, or materialized view without explicit scope approval.

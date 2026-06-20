# USERS MODULE KNOWLEDGE BASE

## OVERVIEW

Users owns account state and the PRD public mypage API scope. Auth still consumes users application contracts during login/signup and withdrawal orchestration.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Provision command | `application/commands/provision/use_case.py` | Creates or resolves service users through a repository port. |
| Provision DTOs | `application/commands/provision/command.py`, `application/commands/provision/result.py` | Command/result contract consumed by auth wiring. |
| Delete command | `application/commands/delete/use_case.py` | Deletes service users through a repository port. |
| Repository port | `application/ports/user_repository.py` | Users application boundary. |
| Domain entity | `domain/model.py` | Minimal `User` entity and factory. |
| Persistence | `infrastructure/persistence/` | SQLAlchemy ORM, mapper, repository. |
| Runtime wiring | `dependencies.py` | Command use case builders for shared-session auth wiring. |
| Future public API | `api/` | Approved PRD surface belongs here when the product behavior todo is implemented. |
| Tests | `tests/test_architecture.py` | Current guardrail is architecture-only. |

## CONVENTIONS

- Users public API scope is reopened for this PRD and planned in the users BC.
- Users owns the PRD public mypage API scope:
  `GET /api/v1/users/me`, `PATCH /api/v1/users/me/settings`,
  `POST /api/v1/users/me/push-tokens`, and
  `DELETE /api/v1/users/me/push-tokens/{deviceId}`.
- This guidance reserves scope only; product behavior must be implemented in the later PRD todo with focused tests.
- User command flows live under `application/commands/<business_task>/{command.py,result.py?,use_case.py}`.
- Internal side-effect-free read flows, if later needed, live under `application/queries/<read_task>/{query.py,result.py?,use_case.py}`.
- `read_models` is reserved for public optimized read API/read model surfaces and is not required for internal queries.
- Application DTO files are named by role (`command.py`, `query.py`, `result.py`), not generic `schemas.py`; future API transport schemas may use `api/schemas.py`.
- Migrated flow use cases use `*CommandUseCase` or `*QueryUseCase`, not generic `*UseCase`.
- `auth` may use `app.modules.users.application.commands.provision.*` and `app.modules.users.dependencies`.
- `get_provision_user_command_use_case(session_provider)` is the cross-module entry point for auth's shared transaction session.
- `domain/model.py` stays persistence-free and framework-free.
- SQLAlchemy details stay inside `infrastructure/persistence`.
- If adding users behavior, add focused functionality tests; current coverage is mostly architecture guardrail.
- Do not add command bus/query bus, event sourcing, outbox, external message bus, Kafka/RabbitMQ/Celery, separate read DB, read-store, projection worker, or materialized view without explicit scope approval.

## ANTI-PATTERNS

- Do not expose users profile/settings/push behavior from auth routes or auth application code.
- Do not let auth import `users.infrastructure`.
- Do not put users-specific coupling rules in the root file unless they become repo-wide policy.

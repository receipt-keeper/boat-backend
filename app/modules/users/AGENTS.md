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
| Public app API | `api/router.py`, `api/schemas.py` | `GET/PATCH/DELETE /api/v1/users/me` (내 정보 조회/수정, 회원 탈퇴). |
| Read/update flows | `application/queries/current_user_profile/`, `application/commands/update_settings/` | `GET`·`PATCH /me`가 사용하는 내부 흐름. |
| Withdrawal route | `api/router.py` `DELETE /me` | auth `WithdrawAccountCommandUseCase`(auth.dependencies)에 위임해 한 트랜잭션으로 삭제/롤백. |
| Tests | `tests/test_api.py`, `tests/test_architecture.py` | 공개 계약·아키텍처 가드. |

## CONVENTIONS

- Users public API scope is reopened for this PRD and implemented in the users BC.
- Users owns the PRD public mypage API scope:
  `GET /api/v1/users/me`, `PATCH /api/v1/users/me`, and
  `DELETE /api/v1/users/me`.
- `GET /me` exposes only app-needed fields (email, name, nickname, profileImageUrl,
  marketingConsent, freeAnalysisTokensRemaining); `PATCH /me` updates `marketingConsent` only.
- `DELETE /me` is the app withdrawal route; it delegates to auth's
  `WithdrawAccountCommandUseCase` and must preserve full-account deletion with rollback.
- Push-token endpoints and push/notification response fields stay out of the app contract
  until the notification feature is approved.
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

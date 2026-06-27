# USERS MODULE KNOWLEDGE BASE

## OVERVIEW

Users는 account state와 PRD public mypage API scope를 소유한다. Auth는 login/signup과 withdrawal orchestration에서 users application contract를 사용한다.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Provision command | `application/commands/provision/use_case.py` | repository port를 통해 service user를 만들거나 찾는다. |
| Resolve-for-login command | `application/commands/resolve_user_for_login/use_case.py` | auth login이 쓰는 provider-neutral user resolution contract. |
| Delete command | `application/commands/delete/use_case.py` | repository port를 통해 service user를 삭제한다. |
| Withdrawal cleanup | `application/commands/withdrawal_cleanup/use_case.py` | withdrawal orchestration에서 users-owned cleanup을 수행한다. |
| Repository port | `application/ports/user_repository.py` | users application boundary. |
| Profile image validator | `application/ports/profile_image_file_validator.py` | files metadata 검증을 application port로 격리한다. |
| Domain entity | `domain/model.py` | `User`, `UserSettings` entity와 factory. |
| Persistence | `infrastructure/persistence/` | SQLAlchemy ORM, mapper, repository. |
| Runtime wiring | `dependencies.py` | command/query use case builder와 shared-session auth wiring. |
| Public app API | `api/router.py`, `api/schemas.py` | `GET/DELETE /api/v1/users/me`, `PUT/DELETE /api/v1/users/me/profile-image`. |
| Read flows | `application/queries/current_user_profile/` | `GET /me` 내부 조회 흐름. |
| Profile image routes | `api/router.py` `/me/profile-image` | files upload 결과를 profile image로 참조한다. |
| Withdrawal route | `api/router.py` `DELETE /me` | auth `WithdrawAccountCommandUseCase`에 위임해 한 transaction에서 삭제/rollback한다. |
| File reference guard | `dependencies.py` | `get_profile_image_file_reference_guard()`가 app-level override로 files delete guard를 대체한다. |
| Tests | `tests/test_api.py`, `tests/test_architecture.py` | 공개 계약과 architecture guard. |

## CONVENTIONS

- Users public API scope is reopened for this PRD and implemented in the users BC.
- Users owns the PRD public mypage profile scope:
  `GET /api/v1/users/me` and `DELETE /api/v1/users/me`.
- Users also owns profile image attachment state:
  `PUT /api/v1/users/me/profile-image` and `DELETE /api/v1/users/me/profile-image`.
- `GET /me`는 profile field만 노출한다: email, name, nickname, profileImageUrl.
- Profile image URL은 API-prefixed response path다. storage key가 아니다.
- Notification settings, marketing notification consent, push device token은 notifications BC 소유다.
- `DELETE /me`는 app withdrawal route다. auth `WithdrawAccountCommandUseCase`에 위임하고 full-account deletion rollback을 보존해야 한다.
- Profile-image reference check는 users 소유지만, files deletion에는 `app.main` dependency override로 주입한다.
- Push-token endpoint와 push/notification response field는 notification feature 승인 전까지 app contract에 넣지 않는다.
- User command flow는 `application/commands/<business_task>/{command.py,result.py?,use_case.py}`를 쓴다.
- 내부 side-effect-free read flow는 `application/queries/<read_task>/{query.py,result.py?,use_case.py}`를 쓴다.
- `read_models`는 public optimized read API/read model surface용이다. 내부 query에는 요구하지 않는다.
- Application DTO file은 역할명으로 둔다. API transport schema는 `api/schemas.py` 가능.
- Migrated flow use case는 `*CommandUseCase` 또는 `*QueryUseCase`를 쓴다.
- `auth`는 `app.modules.users.application.commands.*`와 `app.modules.users.dependencies`를 사용할 수 있다.
- `domain/model.py`는 persistence-free, framework-free를 유지한다.
- SQLAlchemy detail은 `infrastructure/persistence` 안에 둔다.
- users behavior를 추가하면 focused functionality test와 architecture guard를 같이 갱신한다.
- Command bus/query bus, event sourcing, outbox, external message bus, Kafka/RabbitMQ/Celery, separate read DB, read-store, projection worker, materialized view는 명시 승인 없이는 추가하지 않는다.

## ANTI-PATTERNS

- users profile/settings/push behavior를 auth route나 auth application code에서 노출하지 않는다.
- auth가 `users.infrastructure`를 import하게 만들지 않는다.
- users API에서 file storage key, bucket, signed URL, storage adapter name을 노출하지 않는다.
- users application/domain이 `files.infrastructure`를 import하지 않는다.
- users-specific coupling rule이 repo-wide policy가 되기 전까지 root file에 올리지 않는다.

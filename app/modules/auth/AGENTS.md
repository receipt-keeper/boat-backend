# AUTH MODULE KNOWLEDGE BASE

## OVERVIEW

Auth module for external identity verification, backend-issued access JWTs, opaque refresh tokens, and bearer principal restoration.

## STRUCTURE

```text
auth/
├── api/              # /auth routes, transport schemas, auth-specific exception handlers, security deps
├── application/      # commands, queries, principal model, and provider-neutral ports
├── domain/           # credential, external identity, refresh token entities and value objects
├── infrastructure/   # Firebase, JWT, opaque refresh token, SQLAlchemy adapters
├── dependencies.py   # shared transaction session and cross-module users provisioning wiring
└── tests/            # API, service, dependency, security, architecture guards
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Routes | `api/router.py` | `POST /login`, `POST /refresh`, `POST /logout`. |
| Principal deps | `api/security.py` | Bearer extraction and role guard. |
| Auth errors | `api/exception_handlers.py` | 401/403 failure envelopes. |
| Login command | `application/commands/login/use_case.py` | Verify identity, provision user, create credentials, issue tokens. |
| Refresh command | `application/commands/refresh/use_case.py` | Rotate refresh token and issue a new access token pair. |
| Logout command | `application/commands/logout/use_case.py` | Revoke the presented refresh token. |
| Withdraw command | `application/commands/withdraw/use_case.py` | Delete auth credentials and request user deletion/cleanup. |
| Current principal query | `application/queries/current_principal/use_case.py` | Restore bearer principal and verify active credentials without side effects. |
| Token contracts | `application/ports/token_issuer.py` | Provider-neutral access/refresh token ports. |
| Runtime wiring | `dependencies.py` | One transaction session shared across credential and user provisioning. |
| Persistence | `infrastructure/persistence/` | ORM, mapper, credential repository. |
| Provider adapter | `infrastructure/identity_providers/firebase.py` | Firebase SDK is isolated here. |
| Regression guard | `tests/test_architecture.py` | File layout and forbidden import rules. |

## CONVENTIONS

- Keep auth application command packages under `application/commands/<business_task>/`.
- Keep internal side-effect-free auth read flows under `application/queries/<read_task>/`.
- Application DTO files are named by role (`command.py`, `query.py`, `result.py`), not generic `schemas.py`; API transport schemas may remain in `api/schemas.py`.
- Migrated flow use cases use `*CommandUseCase` or `*QueryUseCase`, not generic `*UseCase`.
- `read_models` is reserved for public optimized read API/read model surfaces; it is not required for internal auth queries.
- Auth uses the primary application database by default. A separate read DB,
  read-store, projection worker, or materialized view is forbidden without an
  explicitly approved infrastructure plan.
- Command bus/query bus is forbidden unless explicitly approved later.
- Same-process domain event dispatch is allowed only for concrete side effects
  through `app.core.domain.events.DomainEvent` and
  `app.core.application.event_dispatcher.EventDispatcher`.
- Application code depends on ports and domain objects only; it must not import Firebase, JWT, SQLAlchemy, auth infrastructure, or users infrastructure.
- Token ports stay provider-neutral: issuer/verifier/hasher interfaces, no JWT-specific names in the contract.
- `dependencies.py` is the only place that bridges auth to users provisioning.
- `get_auth_transaction_session()` commits after success and rolls back on any `BaseException`; preserve this when changing signup/login wiring.
- Firebase verification runs through `asyncio.to_thread()` because the SDK call is synchronous.
- Auth domain messages are Korean and domain exceptions remain HTTP-agnostic.
- Access tokens are backend-issued JWTs; refresh tokens are opaque and persisted only by hash.

## ANTI-PATTERNS

- Do not add `logout-all`.
- Do not add Firebase custom-token issuance or direct Apple OIDC verification unless the scope is explicitly reopened.
- users public API belongs to the users BC. Do not mount users endpoints in the auth router.
- Do not import `app.modules.users.infrastructure` from auth.
- Do not create `app/composition` for auth/users wiring.
- Do not reintroduce old file names blocked by `tests/test_architecture.py`.
- Do not move business decisions into Firebase, JWT, or SQLAlchemy adapters.
- NoOpPushCleanup cannot satisfy PRD-complete withdrawal; it must not be used to claim PRD-complete withdrawal cleanup, and missing BC cleanup must remain unclaimed until the real owning BC and cleanup contract exist.
- Do not introduce event sourcing, durable event stores, outbox, retry, replay,
  external message bus, Kafka/RabbitMQ/Celery, cross-process delivery, or
  durability semantics in auth.
- Do not add empty event scaffolding; auth events need a real emitted event and a
  synchronous in-process handler.

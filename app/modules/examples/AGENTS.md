# EXAMPLES MODULE KNOWLEDGE BASE

## OVERVIEW

Reference module for the repo's vertical-slice pattern. Treat it as executable documentation, not as a production persistence model.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Endpoints | `api/router.py` | Example create/get routes and error response docs. |
| Transport schemas | `api/schemas.py` | Request/response shapes only. |
| Use case service | `application/service.py` | Orchestrates entity creation, repository save/get, event dispatch. |
| Domain model | `domain/model.py` | `ExampleUser.create()` validates through value objects. |
| Domain events | `domain/events.py` | Example event recording pattern. |
| Value objects | `domain/value_objects.py` | Own field rules and Korean messages. |
| Repository | `infrastructure/repository.py` | In-memory demo repository. |
| DI | `dependencies.py` | Demo repository + event dispatcher wiring. |
| Tests | `tests/` | Envelope, validation aggregation, OpenAPI docs, event dispatch. |

## CONVENTIONS

- Use this module as the template for new module shape: `api`, `application`, `domain`, `infrastructure`, `tests`, `dependencies.py`.
- Request schemas stay transport-only; domain validation belongs in value objects and `create()` factories.
- `ExampleUserService` dispatches domain events after save; keep event pull/dispatch ordering explicit.
- Module tests override the service through `tests/conftest.py` and clear overrides after each test.
- OpenAPI error response docs are part of the module API contract.

## ANTI-PATTERNS

- Do not copy `ExampleUserRepository`'s `ClassVar` in-memory storage into real modules.
- Do not treat example entity fields or messages as business requirements for other domains.
- Do not expand examples with production-only concerns unless the example is intentionally updated as a template.

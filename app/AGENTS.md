# APP KNOWLEDGE BASE

## OVERVIEW

FastAPI source tree. `app/main.py` composes runtime state, routers, and exception handlers; child packages own platform code and domain modules.

## STRUCTURE

```text
app/
├── main.py       # create_app(), lifespan, router registration, exception handler registration
├── core/         # shared platform primitives
└── modules/      # vertical domain modules
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| App factory | `main.py` | `create_app(settings)` is the entry point. |
| DB state | `main.py` | Lifespan creates `engine` and `session_factory` on `app.state`. |
| Router registration | `main.py` | Auth/examples use `resolved_settings.api_prefix`; health has no API prefix. |
| Exception mapping | `main.py` | Register specific handlers before generic `DomainError` and catch-all handlers. |
| Shared primitives | `core/` | Modules can depend on core. |
| Business slices | `modules/` | Cross-module wiring stays in module `dependencies.py`. |

## CONVENTIONS

- Keep `app/main.py` as the composition root. It should stay small, explicit, and import only routers, handlers, settings, and DB builders.
- DB engine/session factory creation belongs in lifespan, not import time.
- Store runtime objects on `app.state` only when they are created by app composition.
- Router modules own HTTP endpoint behavior; `app/main.py` only includes routers.
- Business APIs normally return `CommonResponse`; `/health` is an operational probe and stays outside the envelope.
- If adding a module router, include it in `create_app()` with `prefix=resolved_settings.api_prefix`.
- If adding a domain error category, add the core category first, then register HTTP mapping here.

## ANTI-PATTERNS

- Do not add an `app/composition` package.
- Do not create global DB engines, session factories, SDK clients, or settings-dependent runtime objects at import time.
- Do not put module-specific dependency graphs in `main.py`; put them in `app/modules/<module>/dependencies.py`.
- Do not make `app/core` depend on `app/modules`.

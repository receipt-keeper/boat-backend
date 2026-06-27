# Boat Backend

Receipt Keeper backend API built with Python, FastAPI, uv, PostgreSQL, and a
strict modular monolith foundation.

## Local Setup

```bash
uv sync
cp .env.example .env
uv run fastapi dev app/main.py
```

The API exposes:

- `GET /health`
- `GET /docs`
- `GET /openapi.json`

## Verification

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

## Architecture

The application uses one deployable FastAPI service with strict internal module
boundaries.

Current initial setup scope:

- `alembic`: database schema migration environment
- `app/main.py`: FastAPI entrypoint, composition root, lifespan-owned DB lifecycle, route wiring, and global exception handler registration
- `app/core/config`: global settings
- `app/core/db`: SQLAlchemy async base and session factories
- `app/core/domain`: shared domain primitives currently limited to `Entity`
- `app/core/domain/exceptions.py`: base domain exception state shared by modules
- `app/core/http`: shared HTTP response models and exception-to-response adapters
- `app/core/observability`: operational probes
- `app/modules/<bounded_context>`: vertical product domain modules

Product modules follow this boundary shape:

```text
app/modules/<bounded_context>/
  api/
  application/
  domain/
  infrastructure/
```

Modules own their application/domain-specific errors and inherit from
`app.core.domain.exceptions`. `app/main.py` wires those handlers into the FastAPI
application.

## API Envelope

Application API routes under `/api/v1` return `CommonResponse[T]`; only `data`
changes by route or error type.

```json
{
  "success": true,
  "status": 200,
  "data": {
    "id": "4fe7798e-dc09-4f42-8ddc-8a9222ed40a8",
    "nickname": "user",
    "email": "user@test.com"
  }
}
```

Failures are normalized by globally registered exception handlers:

```json
{
  "success": false,
  "status": 422,
  "data": {
    "timestamp": "2026-06-01T00:00:00",
    "message": "입력값이 올바르지 않습니다.",
    "path": "/api/v1/users/me",
    "errors": [
      {
        "field": "email",
        "message": "이메일 형식이 올바르지 않습니다."
      }
    ]
  }
}
```

`/health` is kept outside the API envelope because it is an operational probe,
not a business API response.

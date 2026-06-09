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
- `GET /api/v1/examples/{example_user_id}`
- `POST /api/v1/examples`
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
- `app/main.py`: FastAPI composition root and lifespan-owned DB lifecycle
- `app/core/config`: global settings
- `app/core/db`: SQLAlchemy async base and session factories
- `app/core/domain`: shared domain primitives currently limited to `Entity`
- `app/core/http`: exceptions, handlers, and response envelopes
- `app/core/observability`: operational probes
- `app/modules/examples`: sample bounded-context module

The `examples` module is a replaceable sample bounded context. Real product
modules should follow the same boundary shape once their database schemas are
decided:

```text
app/modules/<bounded_context>/
  api/
  application/
  domain/
  infrastructure/
```

## API Envelope

Application API routes under `/api/v1` return `CommonResponse[T]`; only `data`
changes by route or error type.

```json
{
  "success": true,
  "status": 200,
  "data": {
    "id": "4fe7798e-dc09-4f42-8ddc-8a9222ed40a8",
    "nickname": "created-user",
    "email": "created@test.com"
  }
}
```

Failures are normalized by global exception handlers:

```json
{
  "success": false,
  "status": 400,
  "data": {
    "timestamp": "2026-06-01T00:00:00",
    "message": "잘못된 요청입니다.",
    "path": "/api/v1/examples",
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

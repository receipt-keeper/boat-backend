# FILES MODULE KNOWLEDGE BASE

## OVERVIEW

Files는 업로드 이미지 metadata, local object storage 접근, content streaming, delete safety check를 소유한다. mock contract가 아니라 production vertical slice다.

## STRUCTURE

```text
files/
├── api/                 # /files routes, transport schemas, upload validation
├── application/         # upload/delete commands, get/open queries, ports
├── domain/              # file metadata entity, storage/content value objects, exceptions
├── infrastructure/      # SQLAlchemy persistence + local object storage adapter
├── dependencies.py      # repository/storage/unit-of-work/reference-guard wiring
└── tests/               # API, domain/schema, storage, architecture, support helpers
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Routes | `api/router.py` | `POST /files`, `GET /files/{id}`, `GET /files/{id}/content`, `DELETE /files/{id}`. |
| Upload validation | `api/upload_validation.py` | `Settings`의 count, size, content-type policy를 적용한다. |
| Transport schemas | `api/schemas.py` | public response field는 API path를 사용한다. storage 내부값은 숨긴다. |
| Upload command | `application/commands/upload_file/use_case.py` | metadata 저장과 object storage write를 하나의 unit of work로 묶는다. |
| Delete command | `application/commands/delete_file/use_case.py` | ownership, reference guard, storage delete, repository delete를 수행한다. |
| Metadata query | `application/queries/get_file/use_case.py` | user-scoped metadata lookup. |
| Content query | `application/queries/open_file_content/use_case.py` | streaming response용 user-scoped storage read. |
| Ports | `application/ports/` | `FileRepository`, `ObjectStorage`, `FileReferenceGuard`. |
| Local storage | `infrastructure/storage/local.py` | `anyio.to_thread.run_sync` 사용. storage key path containment 검증. |
| Runtime wiring | `dependencies.py` | default delete guard는 허용형이다. `app.main`이 users profile-image guard로 override한다. |
| Regression guard | `tests/test_architecture.py` | layout, Settings fields, foreign infrastructure import, API leak checks. |
| API helpers | `tests/api_support.py` | files API test용 seeded user/auth headers/storage root helper. |

## CONVENTIONS

- File settings는 `Settings`에 둔다: `file_storage_backend`, `file_storage_root`, `file_max_upload_bytes`, `file_max_upload_count`, `file_allowed_content_types`.
- API response는 API prefix가 붙은 `contentPath`를 노출한다. `storage_key`, bucket, CDN, signed URL 개념은 노출하지 않는다.
- `ObjectStorage`는 application port다. local filesystem behavior는 infrastructure adapter다.
- local filesystem I/O는 `anyio.to_thread.run_sync`로 event loop 밖에서 실행한다.
- delete safety는 `FileReferenceGuard` port다. users가 profile-image reference 구현을 app-level override로 제공한다.
- Files application/domain은 user-owned UUID를 알 수 있지만 auth/users infrastructure는 import하지 않는다.
- core application의 `UnitOfWork`와 core DB의 SQLAlchemy 구현을 쓴다. files-local session scope를 만들지 않는다.
- Multipart OpenAPI example은 앱 개발자가 이해하기 쉬운 한글 계약 문구로 유지한다.

## ANTI-PATTERNS

- `application/service.py`, `application/schemas.py`, `infrastructure/repository.py`를 쓰지 않는다. architecture tests가 old shape를 금지한다.
- storage adapter detail을 API schema나 OpenAPI example에 넣지 않는다.
- delete 시 `FileReferenceGuard`를 우회하지 않는다.
- files application/domain에서 `app.modules.auth.infrastructure` 또는 `app.modules.users.infrastructure`를 직접 import하지 않는다.
- local file path를 user-controlled로 만들지 않는다. `StorageKey` validation과 root containment check를 거친다.

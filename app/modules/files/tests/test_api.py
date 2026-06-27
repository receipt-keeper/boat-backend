from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.files.infrastructure.persistence import orm as files_orm
from app.modules.files.tests.api_support import (
    IMAGE_BYTES,
    api_client,
    auth_headers,
    make_test_settings,
    seed_user,
    stored_local_files,
)


def _first_uploaded_file(response_json: dict[str, object]) -> dict[str, object]:
    data = response_json["data"]
    assert isinstance(data, dict)
    files = data["files"]
    assert isinstance(files, list)
    first_file = files[0]
    assert isinstance(first_file, dict)
    return first_file


async def test_file_endpoints_require_bearer_token(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    settings = make_test_settings(tmp_path / "files")

    async with api_client(postgres_session_factory, settings) as client:
        response = await client.post(
            "/api/v1/files",
            files=[("files", ("profile.png", IMAGE_BYTES, "image/png"))],
        )

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
    assert body["status"] == 401
    assert body["data"]["path"] == "/api/v1/files"


async def test_upload_download_and_delete_file_through_api(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-owner",
            email="files-owner@example.com",
            name="파일 소유자",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        upload_response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files=[("files", ("profile.png", IMAGE_BYTES, "image/png"))],
        )
        upload_body = upload_response.json()
        uploaded_file = _first_uploaded_file(upload_body)
        file_id = uploaded_file["fileId"]
        assert isinstance(file_id, str)
        metadata_response = await client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers(seeded),
        )
        content_response = await client.get(
            f"/api/v1/files/{file_id}/content",
            headers=auth_headers(seeded),
        )
        delete_response = await client.delete(
            f"/api/v1/files/{file_id}",
            headers=auth_headers(seeded),
        )
        get_after_delete_response = await client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers(seeded),
        )

    assert upload_response.status_code == 201
    assert upload_body["success"] is True
    assert upload_body["status"] == 201
    assert set(upload_body["data"]) == {"files"}
    assert set(uploaded_file) == {
        "fileId",
        "originalName",
        "contentType",
        "size",
        "contentPath",
    }
    assert uploaded_file["originalName"] == "profile.png"
    assert uploaded_file["contentType"] == "image/png"
    assert uploaded_file["size"] == len(IMAGE_BYTES)
    assert uploaded_file["contentPath"] == f"/api/v1/files/{file_id}/content"
    assert "storage_key" not in upload_response.text
    assert str(storage_root) not in upload_response.text

    metadata_body = metadata_response.json()
    assert metadata_response.status_code == 200
    assert metadata_body["data"] == {
        "fileId": file_id,
        "originalName": "profile.png",
        "contentType": "image/png",
        "size": len(IMAGE_BYTES),
        "contentPath": f"/api/v1/files/{file_id}/content",
    }
    assert "storage_key" not in metadata_response.text
    assert str(storage_root) not in metadata_response.text

    assert content_response.status_code == 200
    assert content_response.headers["content-type"] == "image/png"
    assert content_response.headers["x-content-type-options"] == "nosniff"
    assert content_response.content == IMAGE_BYTES
    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert get_after_delete_response.status_code == 404
    assert stored_local_files(storage_root) == []

    async with postgres_session_factory() as session:
        stored_file = await session.get(files_orm.File, UUID(file_id))
    assert stored_file is None


async def test_file_response_paths_follow_configured_api_prefix(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root, api_prefix="/backend")
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-prefix-owner",
            email="files-prefix-owner@example.com",
            name="파일 prefix 사용자",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        upload_response = await client.post(
            "/backend/files",
            headers=auth_headers(seeded),
            files=[("files", ("profile.png", IMAGE_BYTES, "image/png"))],
        )
        uploaded_file = _first_uploaded_file(upload_response.json())
        file_id = uploaded_file["fileId"]
        metadata_response = await client.get(
            f"/backend/files/{file_id}",
            headers=auth_headers(seeded),
        )

    assert uploaded_file["contentPath"] == f"/backend/files/{file_id}/content"
    assert metadata_response.json()["data"]["contentPath"] == f"/backend/files/{file_id}/content"


async def test_upload_accepts_multiple_files_through_single_request(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-multiple-owner",
            email="files-multiple-owner@example.com",
            name="다중 업로드 사용자",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files=[
                ("files", ("receipt-1.png", IMAGE_BYTES, "image/png")),
                ("files", ("receipt-2.png", IMAGE_BYTES, "image/png")),
            ],
        )

    body = response.json()
    uploaded_files = body["data"]["files"]
    assert response.status_code == 201
    assert len(uploaded_files) == 2
    assert [uploaded_file["originalName"] for uploaded_file in uploaded_files] == [
        "receipt-1.png",
        "receipt-2.png",
    ]
    assert len(stored_local_files(storage_root)) == 2


async def test_upload_rejects_unsupported_content_type(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-invalid-type",
            email="files-invalid-type@example.com",
            name="파일 타입 실패",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files=[("files", ("profile.gif", b"gif-bytes", "image/gif"))],
        )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["errors"] == [
        {"field": "contentType", "message": "지원하지 않는 이미지 형식입니다."}
    ]
    assert stored_local_files(storage_root) == []


async def test_upload_rejects_oversized_file(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root, max_upload_bytes=8)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-too-large",
            email="files-too-large@example.com",
            name="파일 크기 실패",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files=[("files", ("profile.png", IMAGE_BYTES, "image/png"))],
        )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["errors"] == [
        {"field": "size", "message": "파일 크기는 8B 이하여야 합니다."}
    ]
    assert stored_local_files(storage_root) == []


async def test_other_user_cannot_read_or_delete_file(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    settings = make_test_settings(tmp_path / "files")
    async with postgres_session_factory() as session, session.begin():
        owner = await seed_user(
            session,
            subject="files-owner-private",
            email="files-owner-private@example.com",
            name="파일 소유자",
            settings=settings,
        )
        other = await seed_user(
            session,
            subject="files-other-private",
            email="files-other-private@example.com",
            name="다른 사용자",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        upload_response = await client.post(
            "/api/v1/files",
            headers=auth_headers(owner),
            files=[("files", ("profile.png", IMAGE_BYTES, "image/png"))],
        )
        file_id = _first_uploaded_file(upload_response.json())["fileId"]
        assert isinstance(file_id, str)
        metadata_response = await client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers(other),
        )
        content_response = await client.get(
            f"/api/v1/files/{file_id}/content",
            headers=auth_headers(other),
        )
        delete_response = await client.delete(
            f"/api/v1/files/{file_id}",
            headers=auth_headers(other),
        )

    assert metadata_response.status_code == 404
    assert content_response.status_code == 404
    assert delete_response.status_code == 404

    async with postgres_session_factory() as session:
        remaining_file = await session.scalar(
            select(files_orm.File).where(files_orm.File.id == UUID(file_id))
        )
    assert remaining_file is not None

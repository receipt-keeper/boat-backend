from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.files.tests.api_support import (
    api_client,
    auth_headers,
    make_test_settings,
    seed_user,
    stored_local_files,
)


async def test_upload_rejects_spoofed_image_content(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-spoofed-image",
            email="files-spoofed-image@example.com",
            name="파일 위장 실패",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files={"file": ("profile.png", b"not-a-real-png", "image/png")},
        )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["status"] == 422
    assert body["data"]["errors"] == [
        {"field": "contentType", "message": "지원하지 않는 이미지 형식입니다."}
    ]
    assert stored_local_files(storage_root) == []


async def test_upload_rejects_malformed_heif_content(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-malformed-heif",
            email="files-malformed-heif@example.com",
            name="HEIF 위장 실패",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files={
                "file": (
                    "profile.heif",
                    b"\x00\x00\x00\x0cftypheic",
                    "image/heif",
                )
            },
        )

    body = response.json()
    assert response.status_code == 422
    assert body["success"] is False
    assert body["data"]["errors"] == [
        {"field": "contentType", "message": "지원하지 않는 이미지 형식입니다."}
    ]
    assert stored_local_files(storage_root) == []

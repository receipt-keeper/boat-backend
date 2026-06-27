from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.files.tests.api_support import (
    IMAGE_BYTES,
    api_client,
    auth_headers,
    make_test_settings,
    seed_user,
    stored_local_files,
)


async def test_upload_rejects_too_many_files_before_saving(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root, max_upload_count=1)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-too-many-owner",
            email="files-too-many-owner@example.com",
            name="파일 개수 제한 사용자",
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
    assert response.status_code == 422
    assert body["success"] is False
    assert body["data"]["errors"] == [
        {"field": "files", "message": "파일은 최대 1개까지 업로드할 수 있습니다."}
    ]
    assert stored_local_files(storage_root) == []

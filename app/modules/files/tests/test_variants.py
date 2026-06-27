from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.files.domain.value_objects import FileVariant
from app.modules.files.infrastructure.persistence import orm as files_orm
from app.modules.files.tests.api_support import (
    IMAGE_BYTES,
    api_client,
    auth_headers,
    make_test_settings,
    seed_user,
    stored_local_files,
)


async def test_file_metadata_reads_original_variant_when_derivatives_exist(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-variant-reference",
            email="files-variant-reference@example.com",
            name="파일 variant 사용자",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        upload_response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files=[("files", ("profile.png", IMAGE_BYTES, "image/png"))],
        )
        upload_body = upload_response.json()
        assert upload_response.status_code == 201
        assert upload_body["data"]["files"] != []
        file_id = upload_body["data"]["files"][0]["fileId"]

    async with postgres_session_factory() as session, session.begin():
        session.add(
            files_orm.FileObject(
                file_id=UUID(file_id),
                variant_type=FileVariant.THUMBNAIL.value,
                storage_key=f"test/{seeded.user_id}/{file_id}/thumbnail",
                content_type="image/png",
                size=1,
            )
        )

    async with api_client(postgres_session_factory, settings) as client:
        metadata_response = await client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers(seeded),
        )

    body = metadata_response.json()
    assert metadata_response.status_code == 200
    assert body["data"]["contentType"] == "image/png"
    assert body["data"]["size"] == len(IMAGE_BYTES)
    assert stored_local_files(storage_root) != []

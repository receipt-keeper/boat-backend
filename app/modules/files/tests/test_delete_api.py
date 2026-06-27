from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.files.domain.value_objects import FileVariant
from app.modules.files.infrastructure.persistence import orm as files_orm
from app.modules.files.infrastructure.storage.local import LocalObjectStorage
from app.modules.files.tests.api_support import (
    IMAGE_BYTES,
    api_client,
    auth_headers,
    make_test_settings,
    seed_user,
    stored_local_files,
)


async def test_delete_blocks_active_profile_image_reference(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-profile-reference",
            email="files-profile-reference@example.com",
            name="프로필 참조 사용자",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        upload_response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files=[("files", ("profile.png", IMAGE_BYTES, "image/png"))],
        )
        file_id = upload_response.json()["data"]["files"][0]["fileId"]
        set_response = await client.put(
            "/api/v1/users/me/profile-image",
            headers=auth_headers(seeded),
            json={"fileId": file_id},
        )
        delete_response = await client.delete(
            f"/api/v1/files/{file_id}",
            headers=auth_headers(seeded),
        )
        content_response = await client.get(
            f"/api/v1/files/{file_id}/content",
            headers=auth_headers(seeded),
        )

    body = delete_response.json()
    assert set_response.status_code == 200
    assert delete_response.status_code == 409
    assert body["data"]["message"] == "프로필 이미지로 사용 중인 파일은 삭제할 수 없습니다."
    assert content_response.status_code == 200
    assert stored_local_files(storage_root) != []


async def test_delete_removes_all_variant_storage_objects(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "files"
    settings = make_test_settings(storage_root)
    async with postgres_session_factory() as session, session.begin():
        seeded = await seed_user(
            session,
            subject="files-delete-variants",
            email="files-delete-variants@example.com",
            name="variant 삭제 사용자",
            settings=settings,
        )

    async with api_client(postgres_session_factory, settings) as client:
        upload_response = await client.post(
            "/api/v1/files",
            headers=auth_headers(seeded),
            files=[("files", ("profile.png", IMAGE_BYTES, "image/png"))],
        )
        file_id = upload_response.json()["data"]["files"][0]["fileId"]

    thumbnail_key = f"test/{seeded.user_id}/{file_id}/thumbnail"
    storage = LocalObjectStorage(root=str(storage_root))
    stored_thumbnail = await storage.put(key=thumbnail_key, content=b"thumbnail")
    async with postgres_session_factory() as session, session.begin():
        session.add(
            files_orm.FileObject(
                file_id=UUID(file_id),
                variant_type=FileVariant.THUMBNAIL.value,
                storage_key=stored_thumbnail.storage_key,
                content_type="image/png",
                size=stored_thumbnail.size,
                checksum=stored_thumbnail.checksum,
            )
        )

    async with api_client(postgres_session_factory, settings) as client:
        delete_response = await client.delete(
            f"/api/v1/files/{file_id}",
            headers=auth_headers(seeded),
        )

    assert delete_response.status_code == 204
    assert stored_local_files(storage_root) == []

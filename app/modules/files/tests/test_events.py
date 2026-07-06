from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.outbox.orm import OutboxEvent
from app.core.db.outbox.publisher import OutboxEventPublisher
from app.core.db.outbox.serialization import deserialize_event, serialize_event
from app.core.db.unit_of_work import SqlAlchemyUnitOfWork
from app.core.domain.exceptions import ConflictError
from app.modules.files.application.commands.delete_file.command import DeleteFileCommand
from app.modules.files.application.commands.delete_file.use_case import DeleteFileCommandUseCase
from app.modules.files.application.commands.upload_file.command import UploadFileCommand
from app.modules.files.application.commands.upload_file.use_case import UploadFileCommandUseCase
from app.modules.files.application.ports.file_reference_guard import FileReferenceGuard
from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.application.ports.object_storage import ObjectStorage, StoredObject
from app.modules.files.dependencies import build_files_event_registry
from app.modules.files.domain.events import FileDeleted, FileUploaded
from app.modules.files.domain.model import File, FileObject, StoredFile
from app.modules.files.infrastructure.persistence.repository import SqlAlchemyFileRepository


def _sample_file_uploaded() -> FileUploaded:
    return FileUploaded(
        file_id=uuid4(),
        user_id=uuid4(),
        original_name="profile.png",
        content_type="image/png",
        size=1024,
        storage_key="users/abc/files/def/original",
    )


def _sample_file_deleted() -> FileDeleted:
    return FileDeleted(
        file_id=uuid4(),
        user_id=uuid4(),
        storage_keys=[
            "users/abc/files/def/original",
            "users/abc/files/def/thumbnail",
        ],
    )


def test_file_uploaded_round_trips_through_serialization() -> None:
    registry = build_files_event_registry()
    event = _sample_file_uploaded()

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert event_type == "FileUploaded"


def test_file_deleted_round_trips_through_serialization_including_list_payload() -> None:
    registry = build_files_event_registry()
    event = _sample_file_deleted()

    event_type, payload = serialize_event(event)
    restored = deserialize_event(registry, event_type, payload)

    assert restored == event
    assert isinstance(restored, FileDeleted)
    assert restored.storage_keys == event.storage_keys
    assert all(isinstance(key, str) for key in restored.storage_keys)


class _RecordingObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        self.deleted_keys: list[str] = []

    async def put(self, *, key: str, content: bytes) -> StoredObject:
        return StoredObject(storage_key=key, size=len(content), checksum="checksum")

    async def read(self, *, key: str) -> bytes:
        return b""

    async def delete(self, *, key: str) -> None:
        self.deleted_keys.append(key)


class _RecordingEventPublisher:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, events: object) -> None:
        self.published.extend(events)  # type: ignore[arg-type]


class _InMemoryFileRepository(FileRepository):
    def __init__(self, stored_files: list[StoredFile] | None = None) -> None:
        self._stored_files = stored_files or []
        self.deleted_ids: list[UUID] = []

    async def save(self, *, file: File, file_object: FileObject) -> StoredFile:
        stored = StoredFile(file=file, file_object=file_object)
        self._stored_files.append(stored)
        return stored

    async def find_by_id(self, *, file_id: UUID) -> StoredFile | None:
        return next((sf for sf in self._stored_files if sf.file.id == file_id), None)

    async def find_by_id_for_user(self, *, file_id: UUID, user_id: UUID) -> StoredFile | None:
        return next(
            (
                sf
                for sf in self._stored_files
                if sf.file.id == file_id and sf.file.user_id == user_id
            ),
            None,
        )

    async def find_all_by_id_for_user(
        self,
        *,
        file_id: UUID,
        user_id: UUID,
    ) -> tuple[StoredFile, ...]:
        return tuple(
            sf for sf in self._stored_files if sf.file.id == file_id and sf.file.user_id == user_id
        )

    async def delete_by_id(self, *, file_id: UUID) -> None:
        self.deleted_ids.append(file_id)
        self._stored_files = [sf for sf in self._stored_files if sf.file.id != file_id]


class _RejectingFileReferenceGuard(FileReferenceGuard):
    async def ensure_not_referenced(self, *, file_id: UUID) -> None:
        raise ConflictError("프로필 이미지로 사용 중인 파일은 삭제할 수 없습니다.")


async def test_upload_use_case_publishes_file_uploaded_with_finalized_storage_key() -> None:
    repository = _InMemoryFileRepository()
    storage = _RecordingObjectStorage()
    publisher = _RecordingEventPublisher()
    use_case = UploadFileCommandUseCase(
        repository,
        storage=storage,
        event_publisher=publisher,  # type: ignore[arg-type]
    )
    user_id = uuid4()

    result = await use_case.execute(
        UploadFileCommand(
            user_id=user_id,
            original_name="profile.png",
            content_type="image/png",
            size=1024,
            content=b"fake-png-bytes",
        )
    )

    assert len(publisher.published) == 1
    published_event = publisher.published[0]
    assert isinstance(published_event, FileUploaded)
    assert published_event.file_id == result.file_id
    assert published_event.user_id == user_id
    assert published_event.original_name == "profile.png"
    assert published_event.content_type == "image/png"
    assert published_event.size == len(b"fake-png-bytes")
    # storage.put()이 반환한 최종 storage_key가 이벤트 payload에 실린다.
    assert published_event.storage_key.startswith(f"users/{user_id}/files/")


async def test_delete_use_case_publishes_file_deleted_with_all_variant_storage_keys() -> None:
    file = File.create(user_id=uuid4(), original_name="profile.png")
    file_object_original = FileObject.create(
        file_id=file.id,
        storage_key="users/x/files/y/original",
        content_type="image/png",
        size=1024,
    )
    file_object_thumbnail = FileObject.create(
        file_id=file.id,
        storage_key="users/x/files/y/thumbnail",
        content_type="image/png",
        size=256,
    )
    repository = _InMemoryFileRepository(
        stored_files=[
            StoredFile(file=file, file_object=file_object_original),
            StoredFile(file=file, file_object=file_object_thumbnail),
        ]
    )
    storage = _RecordingObjectStorage()
    publisher = _RecordingEventPublisher()
    use_case = DeleteFileCommandUseCase(
        repository,
        storage=storage,
        event_publisher=publisher,  # type: ignore[arg-type]
    )

    await use_case.execute(DeleteFileCommand(file_id=file.id, user_id=file.user_id))

    assert len(publisher.published) == 1
    published_event = publisher.published[0]
    assert isinstance(published_event, FileDeleted)
    assert published_event.file_id == file.id
    assert published_event.user_id == file.user_id
    assert set(published_event.storage_keys) == {
        "users/x/files/y/original",
        "users/x/files/y/thumbnail",
    }
    assert set(storage.deleted_keys) == set(published_event.storage_keys)


async def test_delete_use_case_publishes_nothing_when_reference_guard_rejects() -> None:
    file = File.create(user_id=uuid4(), original_name="profile.png")
    file_object = FileObject.create(
        file_id=file.id,
        storage_key="users/x/files/y/original",
        content_type="image/png",
        size=1024,
    )
    repository = _InMemoryFileRepository(
        stored_files=[StoredFile(file=file, file_object=file_object)]
    )
    storage = _RecordingObjectStorage()
    publisher = _RecordingEventPublisher()
    use_case = DeleteFileCommandUseCase(
        repository,
        storage=storage,
        reference_guard=_RejectingFileReferenceGuard(),
        event_publisher=publisher,  # type: ignore[arg-type]
    )

    with pytest.raises(ConflictError):
        await use_case.execute(DeleteFileCommand(file_id=file.id, user_id=file.user_id))

    assert publisher.published == []
    assert storage.deleted_keys == []
    assert repository.deleted_ids == []


async def test_delete_referenced_file_leaves_outbox_without_new_rows(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """참조 중 파일 삭제(ConflictError) 시 outbox row가 0건이어야 한다."""
    registry = build_files_event_registry()

    async with postgres_session_factory() as session, session.begin():
        repository = SqlAlchemyFileRepository(session)
        file = File.create(user_id=uuid4(), original_name="profile.png")
        file_object = FileObject.create(
            file_id=file.id,
            storage_key="users/z/files/w/original",
            content_type="image/png",
            size=1024,
        )
        await repository.save(file=file, file_object=file_object)

    async with postgres_session_factory() as session:
        unit_of_work = SqlAlchemyUnitOfWork(session)
        publisher = OutboxEventPublisher(session=session, registry=registry)
        use_case = DeleteFileCommandUseCase(
            SqlAlchemyFileRepository(session),
            unit_of_work=unit_of_work,
            reference_guard=_RejectingFileReferenceGuard(),
            event_publisher=publisher,
        )
        with pytest.raises(ConflictError):
            await use_case.execute(DeleteFileCommand(file_id=file.id, user_id=file.user_id))
        await session.rollback()

    async with postgres_session_factory() as session:
        rows = (await session.scalars(select(OutboxEvent))).all()

    assert rows == []

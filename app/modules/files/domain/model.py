from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.domain.entity import Entity
from app.core.domain.validation import Notification
from app.modules.files.domain.value_objects import (
    Checksum,
    ContentType,
    FilePurpose,
    FileSize,
    FileStatus,
    FileVariantType,
    OriginalName,
    StorageBackend,
    StorageKey,
)


@dataclass(eq=False)
class File(Entity[UUID]):
    user_id: UUID
    original_name: OriginalName
    purpose: FilePurpose
    status: FileStatus

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        original_name: str,
        purpose: str = "profile_image",
        status: str = "available",
        file_id: UUID | None = None,
    ) -> "File":
        notification = Notification()
        new_original_name = notification.collect(lambda: OriginalName(original_name))
        new_purpose = notification.collect(lambda: FilePurpose(purpose))
        new_status = notification.collect(lambda: FileStatus(status))
        notification.raise_if_any()

        return cls(
            id=file_id or uuid4(),
            user_id=user_id,
            original_name=new_original_name,
            purpose=new_purpose,
            status=new_status,
        )


@dataclass(eq=False)
class FileObject(Entity[UUID]):
    file_id: UUID
    variant_type: FileVariantType
    storage_backend: StorageBackend
    storage_key: StorageKey
    content_type: ContentType
    size: FileSize
    checksum: Checksum | None = None

    @classmethod
    def create(
        cls,
        *,
        file_id: UUID,
        storage_key: str,
        content_type: str,
        size: int,
        variant_type: str = "original",
        storage_backend: str = "local",
        checksum: str | None = None,
        file_object_id: UUID | None = None,
    ) -> "FileObject":
        notification = Notification()
        new_variant_type = notification.collect(lambda: FileVariantType(variant_type))
        new_storage_backend = notification.collect(lambda: StorageBackend(storage_backend))
        new_storage_key = notification.collect(lambda: StorageKey(storage_key))
        new_content_type = notification.collect(lambda: ContentType(content_type))
        new_size = notification.collect(lambda: FileSize(size))
        new_checksum = (
            None if checksum is None else notification.collect(lambda: Checksum(checksum))
        )
        notification.raise_if_any()

        return cls(
            id=file_object_id or uuid4(),
            file_id=file_id,
            variant_type=new_variant_type,
            storage_backend=new_storage_backend,
            storage_key=new_storage_key,
            content_type=new_content_type,
            size=new_size,
            checksum=new_checksum,
        )


@dataclass(frozen=True, slots=True)
class StoredFile:
    file: File
    file_object: FileObject

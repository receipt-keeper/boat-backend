from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.domain.entity import AggregateRoot, Entity
from app.core.domain.validation import Notification
from app.modules.files.domain.events import FileDeleted, FileUploaded
from app.modules.files.domain.value_objects import (
    Checksum,
    ContentType,
    FileSize,
    FileVariant,
    FileVariantType,
    OriginalName,
    StorageKey,
)


@dataclass(eq=False)
class File(AggregateRoot[UUID]):
    user_id: UUID
    original_name: OriginalName

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        original_name: str,
        file_id: UUID | None = None,
    ) -> "File":
        notification = Notification()
        new_original_name = notification.collect(lambda: OriginalName(original_name))
        notification.raise_if_any()

        return cls(
            id=file_id or uuid4(),
            user_id=user_id,
            original_name=new_original_name,
        )

    def record_uploaded(self, *, file_object: "FileObject") -> None:
        """업로드 완료(저장소 반영 후 확정된 `FileObject`)를 이벤트로 기록한다.

        `File.create()` 시점에는 storage_key/content_type/size가 아직 확정되지
        않으므로(업로드 use case가 storage 반영 결과로 `FileObject`를 재생성함),
        이 메서드는 그 확정 시점 이후 use case가 호출한다. 이벤트 생성 자체는
        애그리거트가 소유한다.
        """
        self.record_event(
            FileUploaded(
                file_id=self.id,
                user_id=self.user_id,
                original_name=self.original_name.value,
                content_type=file_object.content_type.value,
                size=file_object.size.value,
                storage_key=file_object.storage_key.value,
            )
        )

    def record_deleted(self, *, storage_keys: list[str]) -> None:
        """삭제 guard 통과 후, 전체 variant의 storage_key 목록으로 기록한다."""
        self.record_event(
            FileDeleted(
                file_id=self.id,
                user_id=self.user_id,
                storage_keys=storage_keys,
            )
        )


@dataclass(eq=False)
class FileObject(Entity[UUID]):
    file_id: UUID
    variant_type: FileVariantType
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
        variant_type: FileVariant = FileVariant.ORIGINAL,
        checksum: str | None = None,
        file_object_id: UUID | None = None,
    ) -> "FileObject":
        notification = Notification()
        new_variant_type = notification.collect(lambda: FileVariantType(variant_type))
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
            storage_key=new_storage_key,
            content_type=new_content_type,
            size=new_size,
            checksum=new_checksum,
        )


@dataclass(frozen=True, slots=True)
class StoredFile:
    file: File
    file_object: FileObject

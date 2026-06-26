from app.modules.files.domain.model import (
    File as DomainFile,
)
from app.modules.files.domain.model import (
    FileObject as DomainFileObject,
)
from app.modules.files.domain.model import (
    StoredFile,
)
from app.modules.files.domain.value_objects import FileVariant
from app.modules.files.infrastructure.persistence import orm


def file_to_domain(record: orm.File) -> DomainFile:
    return DomainFile.create(
        file_id=record.id,
        user_id=record.user_id,
        original_name=record.original_name,
    )


def file_to_record(file: DomainFile) -> orm.File:
    return orm.File(
        id=file.id,
        user_id=file.user_id,
        original_name=file.original_name.value,
    )


def file_object_to_domain(record: orm.FileObject) -> DomainFileObject:
    return DomainFileObject.create(
        file_object_id=record.id,
        file_id=record.file_id,
        variant_type=FileVariant(record.variant_type),
        storage_key=record.storage_key,
        content_type=record.content_type,
        size=record.size,
        checksum=record.checksum,
    )


def file_object_to_record(file_object: DomainFileObject) -> orm.FileObject:
    return orm.FileObject(
        id=file_object.id,
        file_id=file_object.file_id,
        variant_type=file_object.variant_type.value.value,
        storage_key=file_object.storage_key.value,
        content_type=file_object.content_type.value,
        size=file_object.size.value,
        checksum=None if file_object.checksum is None else file_object.checksum.value,
    )


def stored_file_to_domain(
    *,
    file_record: orm.File,
    file_object_record: orm.FileObject,
) -> StoredFile:
    return StoredFile(
        file=file_to_domain(file_record),
        file_object=file_object_to_domain(file_object_record),
    )

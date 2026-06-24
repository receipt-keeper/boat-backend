import importlib
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    BigInteger,
    Constraint,
    ForeignKeyConstraint,
    Index,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID

from app.core.config.settings import Settings
from app.core.db.base import Base
from app.core.domain.exceptions import ValidationError
from app.modules.files.application.commands.upload_file.command import UploadFileCommand
from app.modules.files.application.commands.upload_file.use_case import UploadFileCommandUseCase
from app.modules.files.application.ports.file_repository import FileRepository
from app.modules.files.domain.model import File, FileObject, StoredFile


def test_files_schema_tables_columns_constraints_and_indexes_are_declared() -> None:
    _import_files_orm()

    metadata = Base.metadata

    assert {"files", "file_objects"}.issubset(metadata.tables)

    files = metadata.tables["files"]
    file_objects = metadata.tables["file_objects"]

    assert set(files.columns.keys()) == {
        "id",
        "user_id",
        "original_name",
        "purpose",
        "status",
        "created_at",
        "updated_at",
    }
    assert isinstance(files.columns["id"].type, PostgreSQLUUID)
    assert isinstance(files.columns["user_id"].type, PostgreSQLUUID)
    assert _string_length(files, "original_name") == 255
    assert _string_length(files, "purpose") == 50
    assert _string_length(files, "status") == 50
    assert files.columns["user_id"].nullable is False
    assert files.columns["original_name"].nullable is False
    assert _has_index(files.indexes, ("user_id", "created_at"), unique=False)

    assert set(file_objects.columns.keys()) == {
        "id",
        "file_id",
        "variant_type",
        "storage_backend",
        "storage_key",
        "content_type",
        "size",
        "checksum",
        "created_at",
        "updated_at",
    }
    assert isinstance(file_objects.columns["id"].type, PostgreSQLUUID)
    assert isinstance(file_objects.columns["file_id"].type, PostgreSQLUUID)
    assert _string_length(file_objects, "variant_type") == 50
    assert _string_length(file_objects, "storage_backend") == 50
    assert _string_length(file_objects, "storage_key") == 500
    assert _string_length(file_objects, "content_type") == 100
    assert isinstance(file_objects.columns["size"].type, BigInteger)
    assert file_objects.columns["file_id"].nullable is False
    assert file_objects.columns["storage_key"].nullable is False
    assert file_objects.columns["checksum"].nullable is True
    assert any(
        _unique_columns(constraint) == ("storage_key",) for constraint in file_objects.constraints
    )
    assert _has_index(file_objects.indexes, ("file_id", "variant_type"), unique=True)


def test_files_schema_uses_only_same_bc_foreign_keys() -> None:
    _import_files_orm()

    files = Base.metadata.tables["files"]
    file_objects = Base.metadata.tables["file_objects"]

    assert files.foreign_keys == set()
    assert {
        (
            tuple(constraint.column_keys),
            tuple(element.column.table.name for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in file_objects.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    } == {(("file_id",), ("files",), "CASCADE")}


def test_file_storage_settings_are_declared_with_local_defaults() -> None:
    settings = Settings()

    assert settings.file_storage_backend == "local"
    assert settings.file_storage_root == "./storage/files"
    assert settings.file_max_upload_bytes == 10_485_760
    assert settings.file_allowed_content_types == (
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
    )


async def test_upload_file_rejects_pdf_content_type_before_persistence_write() -> None:
    repository = RecordingFileRepository()
    use_case = UploadFileCommandUseCase(repository)

    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            UploadFileCommand(
                user_id=uuid4(),
                original_name="profile.pdf",
                storage_key="users/profile.pdf",
                content_type="application/pdf",
                size=1024,
            )
        )

    assert error.value.message == "입력값이 올바르지 않습니다."
    assert [(detail.field, detail.message) for detail in error.value.details] == [
        ("contentType", "지원하지 않는 이미지 형식입니다.")
    ]
    assert repository.save_calls == 0


async def test_upload_file_rejects_configured_max_size_before_persistence_write() -> None:
    repository = RecordingFileRepository()
    use_case = UploadFileCommandUseCase(repository)
    settings = Settings()

    with pytest.raises(ValidationError) as error:
        await use_case.execute(
            UploadFileCommand(
                user_id=uuid4(),
                original_name="profile.png",
                storage_key="users/profile.png",
                content_type="image/png",
                size=settings.file_max_upload_bytes + 1,
            )
        )

    assert error.value.message == "입력값이 올바르지 않습니다."
    assert [(detail.field, detail.message) for detail in error.value.details] == [
        ("size", "파일 크기는 10MB 이하여야 합니다.")
    ]
    assert repository.save_calls == 0


def _import_files_orm() -> None:
    try:
        importlib.import_module("app.modules.files.infrastructure.persistence.orm")
    except ModuleNotFoundError as error:
        raise AssertionError("files BC ORM이 아직 선언되지 않았다") from error


def _string_length(table: Table, column_name: str) -> int | None:
    column_type = table.columns[column_name].type
    if not isinstance(column_type, String):
        return None
    return column_type.length


def _has_index(indexes: set[Index], columns: tuple[str, ...], *, unique: bool) -> bool:
    return any(
        tuple(column.name for column in index.columns) == columns and index.unique is unique
        for index in indexes
    )


def _unique_columns(constraint: Constraint) -> tuple[str, ...]:
    if not isinstance(constraint, UniqueConstraint):
        return ()
    return tuple(column.name for column in constraint.columns)


class RecordingFileRepository(FileRepository):
    def __init__(self) -> None:
        self.save_calls = 0

    async def save(self, *, file: File, file_object: FileObject) -> StoredFile:
        self.save_calls += 1
        return StoredFile(file=file, file_object=file_object)

    async def find_by_id(self, *, file_id: UUID) -> StoredFile | None:
        return None

    async def find_by_id_for_user(self, *, file_id: UUID, user_id: UUID) -> StoredFile | None:
        return None

    async def delete_by_id(self, *, file_id: UUID) -> None:
        return None

from dataclasses import dataclass
from typing import ClassVar

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


@dataclass(frozen=True, slots=True)
class OriginalName(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if (
            not self.value
            or self.value.strip() != self.value
            or "/" in self.value
            or "\\" in self.value
            or len(self.value) > self.MAX_LENGTH
        ):
            raise ValidationError(
                [ErrorDetail(field="originalName", message="파일명이 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class FilePurpose(ValueObject[str]):
    ALLOWED: ClassVar[frozenset[str]] = frozenset({"profile_image"})

    def validate(self) -> None:
        if self.value not in self.ALLOWED:
            raise ValidationError(
                [ErrorDetail(field="purpose", message="파일 용도가 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class FileStatus(ValueObject[str]):
    ALLOWED: ClassVar[frozenset[str]] = frozenset({"pending", "available", "deleted"})

    def validate(self) -> None:
        if self.value not in self.ALLOWED:
            raise ValidationError(
                [ErrorDetail(field="status", message="파일 상태가 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class FileVariantType(ValueObject[str]):
    ALLOWED: ClassVar[frozenset[str]] = frozenset({"original"})

    def validate(self) -> None:
        if self.value not in self.ALLOWED:
            raise ValidationError(
                [ErrorDetail(field="variantType", message="파일 변형 유형이 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class StorageBackend(ValueObject[str]):
    ALLOWED: ClassVar[frozenset[str]] = frozenset({"local"})

    def validate(self) -> None:
        if self.value not in self.ALLOWED:
            raise ValidationError(
                [ErrorDetail(field="storageBackend", message="파일 저장소가 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class StorageKey(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 500

    def validate(self) -> None:
        parts = self.value.split("/")
        if (
            not self.value
            or self.value.startswith("/")
            or "\\" in self.value
            or "" in parts
            or "." in parts
            or ".." in parts
            or len(self.value) > self.MAX_LENGTH
        ):
            raise ValidationError(
                [ErrorDetail(field="storageKey", message="파일 저장 키가 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class ContentType(ValueObject[str]):
    ALLOWED: ClassVar[frozenset[str]] = frozenset(
        {"image/jpeg", "image/png", "image/heic", "image/heif"}
    )
    MAX_LENGTH: ClassVar[int] = 100

    def validate(self) -> None:
        if self.value not in self.ALLOWED or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="contentType", message="지원하지 않는 이미지 형식입니다.")]
            )


@dataclass(frozen=True, slots=True)
class FileSize(ValueObject[int]):
    MAX_BYTES: ClassVar[int] = 10_485_760

    def validate(self) -> None:
        if self.value <= 0 or self.value > self.MAX_BYTES:
            raise ValidationError(
                [ErrorDetail(field="size", message="파일 크기는 10MB 이하여야 합니다.")]
            )


@dataclass(frozen=True, slots=True)
class Checksum(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="checksum", message="파일 체크섬이 올바르지 않습니다.")]
            )

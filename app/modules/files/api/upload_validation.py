from dataclasses import dataclass
from typing import Final

from fastapi import UploadFile

from app.core.domain.exceptions import ErrorDetail, ValidationError

_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE: Final = b"\xff\xd8\xff"
_HEIF_COMPATIBLE_BRANDS: Final = frozenset(
    {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"mif1",
        b"msf1",
    }
)
_HEIF_CONTENT_TYPES: Final = frozenset({"image/heic", "image/heif"})


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    original_name: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class UploadValidationPolicy:
    allowed_content_types: tuple[str, ...]
    max_upload_bytes: int
    max_upload_count: int


async def read_and_validate_uploads(
    *,
    files: list[UploadFile],
    policy: UploadValidationPolicy,
) -> list[ValidatedUpload]:
    if not 1 <= len(files) <= policy.max_upload_count:
        raise ValidationError(
            [
                ErrorDetail(
                    field="files",
                    message=f"파일은 최대 {policy.max_upload_count}개까지 업로드할 수 있습니다.",
                )
            ]
        )

    validated_uploads: list[ValidatedUpload] = []
    for file in files:
        content = await file.read(policy.max_upload_bytes + 1)
        _validate_upload(
            content_type=file.content_type,
            content=content,
            size=len(content),
            allowed_content_types=policy.allowed_content_types,
            max_upload_bytes=policy.max_upload_bytes,
        )
        validated_uploads.append(
            ValidatedUpload(
                original_name=file.filename or "upload",
                content_type=file.content_type or "",
                content=content,
            )
        )
    return validated_uploads


def _validate_upload(
    *,
    content_type: str | None,
    content: bytes,
    size: int,
    allowed_content_types: tuple[str, ...],
    max_upload_bytes: int,
) -> None:
    details: list[ErrorDetail] = []
    if content_type not in allowed_content_types:
        details.append(ErrorDetail(field="contentType", message="지원하지 않는 이미지 형식입니다."))
    if size <= 0 or size > max_upload_bytes:
        details.append(
            ErrorDetail(
                field="size",
                message=f"파일 크기는 {_format_bytes(max_upload_bytes)} 이하여야 합니다.",
            )
        )
    if content_type in allowed_content_types and not _matches_image_content_type(
        content_type=content_type,
        content=content,
    ):
        details.append(ErrorDetail(field="contentType", message="지원하지 않는 이미지 형식입니다."))
    if details:
        raise ValidationError(details)


def _matches_image_content_type(*, content_type: str, content: bytes) -> bool:
    detected_content_type = _detect_image_content_type(content)
    if detected_content_type is None:
        return False
    if detected_content_type in _HEIF_CONTENT_TYPES and content_type in _HEIF_CONTENT_TYPES:
        return True
    return detected_content_type == content_type


def _detect_image_content_type(content: bytes) -> str | None:
    if content.startswith(_PNG_SIGNATURE):
        return "image/png"
    if content.startswith(_JPEG_SIGNATURE):
        return "image/jpeg"
    if len(content) >= 16 and content[4:8] == b"ftyp":
        box_size = int.from_bytes(content[0:4], "big")
        if not 16 <= box_size <= len(content):
            return None
        brands = {content[8:12]} | {
            content[index : index + 4] for index in range(16, box_size - 3, 4)
        }
        if brands & _HEIF_COMPATIBLE_BRANDS:
            return "image/heif"
    return None


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size % 1_048_576 == 0:
        return f"{size // 1_048_576}MB"
    if size % 1024 == 0:
        return f"{size // 1024}KB"
    return f"{size}B"

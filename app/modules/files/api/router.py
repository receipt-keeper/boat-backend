from io import BytesIO
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, File, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.files.api.schemas import FileMetadataResponse, UploadedFileResponse
from app.modules.files.application.commands.delete_file.command import DeleteFileCommand
from app.modules.files.application.commands.upload_file.command import UploadFileCommand
from app.modules.files.application.queries.get_file.query import GetFileQuery
from app.modules.files.application.queries.open_file_content.query import OpenFileContentQuery
from app.modules.files.dependencies import (
    DeleteFileCommandUseCaseDep,
    GetFileQueryUseCaseDep,
    OpenFileContentQueryUseCaseDep,
    UploadFileCommandUseCaseDep,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": CommonResponse[ApiErrorData],
        "description": "인증 실패",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": CommonResponse[ApiErrorData],
        "description": "파일을 찾을 수 없음",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": CommonResponse[ApiErrorData],
        "description": "검증 실패 - 요청 형식 오류 또는 도메인 검증 실패",
    },
}
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

router = APIRouter(
    prefix="/files",
    tags=["files"],
    responses=_ERROR_RESPONSES,
)


@router.post(
    "",
    response_model=CommonResponse[UploadedFileResponse],
    status_code=status.HTTP_201_CREATED,
    summary="파일 업로드",
    description=(
        "이미지 파일을 업로드하고 파일 ID, 파일명, 파일 형식, 크기, 다운로드 경로를 반환한다."
    ),
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "examples": {
                        "image": {
                            "summary": "이미지 업로드",
                            "value": {
                                "file": "image.png",
                            },
                        }
                    }
                }
            }
        }
    },
)
async def upload_file(
    request: Request,
    principal: CurrentPrincipalDep,
    command_use_case: UploadFileCommandUseCaseDep,
    file: Annotated[
        UploadFile,
        File(description="업로드할 이미지 파일.", examples=["image.png"]),
    ],
) -> CommonResponse[UploadedFileResponse]:
    settings = request.app.state.settings
    content = await file.read(settings.file_max_upload_bytes + 1)
    _validate_upload(
        content_type=file.content_type,
        content=content,
        size=len(content),
        allowed_content_types=tuple(settings.file_allowed_content_types),
        max_upload_bytes=settings.file_max_upload_bytes,
    )
    result = await command_use_case.execute(
        UploadFileCommand(
            user_id=principal.user_id,
            original_name=file.filename or "upload",
            content_type=file.content_type or "",
            size=len(content),
            content=content,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_201_CREATED,
        data=UploadedFileResponse(
            fileId=result.file_id,
            originalName=result.original_name,
            contentType=result.content_type,
            size=result.size,
            contentPath=_with_api_prefix(request, result.content_path),
        ),
    )


@router.get(
    "/{file_id}",
    response_model=CommonResponse[FileMetadataResponse],
    summary="파일 정보 조회",
    description="파일 ID에 해당하는 업로드 파일의 이름, 형식, 크기, 다운로드 경로를 조회한다.",
)
async def get_file(
    request: Request,
    file_id: UUID,
    principal: CurrentPrincipalDep,
    query_use_case: GetFileQueryUseCaseDep,
) -> CommonResponse[FileMetadataResponse]:
    result = await query_use_case.execute(GetFileQuery(file_id=file_id, user_id=principal.user_id))
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=FileMetadataResponse(
            fileId=result.file_id,
            originalName=result.original_name,
            contentType=result.content_type,
            size=result.size,
            contentPath=_with_api_prefix(request, result.content_path),
        ),
    )


@router.get(
    "/{file_id}/content",
    summary="파일 다운로드",
    description="파일 ID에 해당하는 업로드 파일을 다운로드한다.",
)
async def get_file_content(
    file_id: UUID,
    principal: CurrentPrincipalDep,
    query_use_case: OpenFileContentQueryUseCaseDep,
) -> StreamingResponse:
    result = await query_use_case.execute(
        OpenFileContentQuery(file_id=file_id, user_id=principal.user_id)
    )
    return StreamingResponse(
        BytesIO(result.content),
        media_type=result.content_type,
        headers={
            "Content-Length": str(result.size),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="파일 삭제",
    description="파일 ID에 해당하는 업로드 파일을 삭제한다.",
)
async def delete_file(
    file_id: UUID,
    principal: CurrentPrincipalDep,
    command_use_case: DeleteFileCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(DeleteFileCommand(file_id=file_id, user_id=principal.user_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brands = {content[index : index + 4] for index in range(8, len(content) - 3, 4)}
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


def _with_api_prefix(request: Request, path: str) -> str:
    api_prefix = request.app.state.settings.api_prefix.rstrip("/")
    return f"{api_prefix}{path}"

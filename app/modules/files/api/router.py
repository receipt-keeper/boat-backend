from io import BytesIO
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status
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

router = APIRouter(
    prefix="/files",
    tags=["files"],
    responses=_ERROR_RESPONSES,
)


@router.post(
    "",
    response_model=CommonResponse[UploadedFileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    request: Request,
    principal: CurrentPrincipalDep,
    command_use_case: UploadFileCommandUseCaseDep,
    file: Annotated[UploadFile, File()],
    purpose: Annotated[str, Form()] = "profile_image",
) -> CommonResponse[UploadedFileResponse]:
    settings = request.app.state.settings
    content = await file.read(settings.file_max_upload_bytes + 1)
    _validate_upload(
        content_type=file.content_type,
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
            purpose=purpose,
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
            purpose=result.purpose,
            status=result.status,
            contentType=result.content_type,
            size=result.size,
            contentPath=_with_api_prefix(request, result.content_path),
        ),
    )


@router.get("/{file_id}/content")
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
        headers={"Content-Length": str(result.size)},
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": CommonResponse[ApiErrorData],
            "description": "프로필 이미지로 사용 중인 파일은 삭제할 수 없음",
        },
    },
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
    if details:
        raise ValidationError(details)


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

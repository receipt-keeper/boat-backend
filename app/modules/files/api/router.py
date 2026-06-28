from io import BytesIO
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.files.api.schemas import (
    FileMetadataResponse,
    UploadedFileResponse,
    UploadedFilesResponse,
)
from app.modules.files.api.upload_validation import (
    UploadValidationPolicy,
    read_and_validate_uploads,
)
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
    response_model=CommonResponse[UploadedFilesResponse],
    status_code=status.HTTP_201_CREATED,
    summary="파일 업로드",
    description=(
        "이미지 파일을 하나 이상 업로드하고 각 파일의 ID, 파일명, "
        "파일 형식, 크기, 다운로드 경로를 반환한다."
    ),
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "examples": {
                        "image": {
                            "summary": "이미지 업로드",
                            "value": {
                                "files": ["receipt-1.png", "receipt-2.png"],
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
    files: Annotated[
        list[UploadFile],
        File(description="업로드할 이미지 파일 목록."),
    ],
) -> CommonResponse[UploadedFilesResponse]:
    settings = request.app.state.settings
    validated_uploads = await read_and_validate_uploads(
        files=files,
        policy=UploadValidationPolicy(
            allowed_content_types=tuple(settings.file_allowed_content_types),
            max_upload_bytes=settings.file_max_upload_bytes,
            max_upload_count=settings.file_max_upload_count,
        ),
    )
    uploaded_files: list[UploadedFileResponse] = []
    for upload in validated_uploads:
        result = await command_use_case.execute(
            UploadFileCommand(
                user_id=principal.user_id,
                original_name=upload.original_name,
                content_type=upload.content_type,
                size=len(upload.content),
                content=upload.content,
            )
        )
        uploaded_files.append(
            UploadedFileResponse(
                fileId=result.file_id,
                originalName=result.original_name,
                contentType=result.content_type,
                size=result.size,
                contentPath=_with_api_prefix(request, result.content_path),
            )
        )
    return CommonResponse(
        success=True,
        status=status.HTTP_201_CREATED,
        data=UploadedFilesResponse(files=uploaded_files),
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
            "Content-Length": str(len(result.content)),
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


def _with_api_prefix(request: Request, path: str) -> str:
    api_prefix = request.app.state.settings.api_prefix.rstrip("/")
    return f"{api_prefix}{path}"

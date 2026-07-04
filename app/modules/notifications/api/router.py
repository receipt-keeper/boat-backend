from datetime import datetime
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse, CursorPaginationResponse
from app.modules.notifications.api.schemas import (
    CreateNotificationRequest,
    NotificationListQuery,
    NotificationListResponse,
    NotificationResponse,
    NotificationSettingsResponse,
    RegisterDeviceRequest,
    UpdateNotificationSettingsRequest,
)
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.mark_notification_read.command import (
    MarkNotificationReadCommand,
)
from app.modules.notifications.application.commands.register_device_token.command import (
    RegisterDeviceTokenCommand,
)
from app.modules.notifications.application.commands.unregister_device_token.command import (
    UnregisterDeviceTokenCommand,
)
from app.modules.notifications.application.commands.update_notification_settings.command import (
    UpdateNotificationSettingsCommand,
)
from app.modules.notifications.application.queries.get_notification_settings.query import (
    GetNotificationSettingsQuery,
)
from app.modules.notifications.application.queries.list_notifications.query import (
    ListNotificationsQuery,
)
from app.modules.notifications.dependencies import (
    CreateNotificationCommandUseCaseDep,
    GetNotificationSettingsQueryUseCaseDep,
    ListNotificationsQueryUseCaseDep,
    MarkNotificationReadCommandUseCaseDep,
    RegisterDeviceTokenCommandUseCaseDep,
    UnregisterDeviceTokenCommandUseCaseDep,
    UpdateNotificationSettingsCommandUseCaseDep,
)
from app.modules.notifications.domain.value_objects import (
    NotificationKind,
    NotificationTargetType,
)


class _NotificationResult(Protocol):
    @property
    def notification_id(self) -> UUID: ...

    @property
    def kind(self) -> NotificationKind: ...

    @property
    def message(self) -> str: ...

    @property
    def target_type(self) -> NotificationTargetType: ...

    @property
    def target_id(self) -> UUID | None: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def read_at(self) -> datetime | None: ...


_OpenApiResponse = dict[str, type[CommonResponse[ApiErrorData]] | str]

_ERROR_RESPONSES: dict[int | str, _OpenApiResponse] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": CommonResponse[ApiErrorData],
        "description": "인증 실패",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": CommonResponse[ApiErrorData],
        "description": "검증 실패 - 요청 형식 오류 또는 도메인 검증 실패",
    },
}
router = APIRouter(
    tags=["notifications"],
    responses=_ERROR_RESPONSES,
)


@router.get(
    "/notifications",
    response_model=CommonResponse[NotificationListResponse],
    summary="알림 목록 조회",
    description="보증 만료, 영수증 등록 안내, 혜택 안내 등 앱 알림을 반환한다.",
)
async def list_notifications(
    query: Annotated[NotificationListQuery, Query()],
    principal: CurrentPrincipalDep,
    query_use_case: ListNotificationsQueryUseCaseDep,
) -> CommonResponse[NotificationListResponse]:
    result = await query_use_case.execute(
        ListNotificationsQuery(
            user_id=principal.user_id,
            cursor=query.cursor,
            limit=query.limit,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=NotificationListResponse(
            notifications=[
                _notification_response(notification) for notification in result.notifications
            ],
            pagination=CursorPaginationResponse(
                nextCursor=result.next_cursor,
                hasNext=result.has_next,
                limit=result.limit,
                totalCount=result.total_count,
            ),
        ),
    )


@router.post(
    "/notifications",
    status_code=status.HTTP_201_CREATED,
    response_model=CommonResponse[NotificationResponse],
    summary="알림 생성",
    description="현재 사용자에게 표시할 앱 알림을 생성한다.",
)
async def create_notification(
    request: CreateNotificationRequest,
    principal: CurrentPrincipalDep,
    command_use_case: CreateNotificationCommandUseCaseDep,
) -> CommonResponse[NotificationResponse]:
    result = await command_use_case.execute(
        CreateNotificationCommand(
            user_id=principal.user_id,
            kind=request.kind,
            message=request.message,
            target_type=request.target_type,
            target_id=request.target_id,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_201_CREATED,
        data=_notification_response(result),
    )


@router.patch(
    "/notifications/settings",
    response_model=CommonResponse[NotificationSettingsResponse],
    summary="알림 설정 수정",
    description="푸시 알림과 마케팅 알림 수신 여부를 수정한다. 보내지 않은 값은 그대로 둔다.",
)
async def update_notification_settings(
    request: UpdateNotificationSettingsRequest,
    principal: CurrentPrincipalDep,
    command_use_case: UpdateNotificationSettingsCommandUseCaseDep,
) -> CommonResponse[NotificationSettingsResponse]:
    result = await command_use_case.execute(
        UpdateNotificationSettingsCommand(
            user_id=principal.user_id,
            push_enabled=request.push_enabled,
            marketing_consent=request.marketing_consent,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=NotificationSettingsResponse(
            pushEnabled=result.push_enabled,
            marketingConsent=result.marketing_consent,
        ),
    )


@router.get(
    "/notifications/settings",
    response_model=CommonResponse[NotificationSettingsResponse],
    summary="알림 설정 조회",
    description="푸시 알림과 마케팅 알림 수신 여부를 반환한다.",
)
async def get_notification_settings(
    principal: CurrentPrincipalDep,
    query_use_case: GetNotificationSettingsQueryUseCaseDep,
) -> CommonResponse[NotificationSettingsResponse]:
    result = await query_use_case.execute(GetNotificationSettingsQuery(user_id=principal.user_id))
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=NotificationSettingsResponse(
            pushEnabled=result.push_enabled,
            marketingConsent=result.marketing_consent,
        ),
    )


@router.patch(
    "/notifications/{notification_id}",
    response_model=CommonResponse[NotificationResponse],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": CommonResponse[ApiErrorData],
            "description": "알림을 찾을 수 없음",
        },
    },
    summary="알림 상태 수정",
    description="알림을 읽은 상태로 바꾸고 변경된 알림 정보를 반환한다.",
)
async def update_notification(
    notification_id: UUID,
    principal: CurrentPrincipalDep,
    command_use_case: MarkNotificationReadCommandUseCaseDep,
) -> CommonResponse[NotificationResponse]:
    result = await command_use_case.execute(
        MarkNotificationReadCommand(
            user_id=principal.user_id,
            notification_id=notification_id,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=_notification_response(result),
    )


@router.put(
    "/notifications/devices",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="FCM 디바이스 등록",
    description=(
        "로그인한 사용자의 디바이스를 FID(Firebase Installation ID)로 등록한다. "
        "같은 FID를 다시 등록하면 플랫폼과 갱신 시각을 덮어쓰는 멱등 upsert이며, "
        "같은 FID가 다른 사용자에게 등록되어 있었다면 이번 사용자 소유로 이전된다. "
        "성공하면 본문 없이 204를 반환한다."
    ),
)
async def register_device(
    request: RegisterDeviceRequest,
    principal: CurrentPrincipalDep,
    command_use_case: RegisterDeviceTokenCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(
        RegisterDeviceTokenCommand(
            user_id=principal.user_id,
            fid=request.fid,
            platform=request.platform,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/notifications/devices/{fid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="FCM 디바이스 해제",
    description=(
        "로그인한 사용자의 디바이스 등록을 FID 기준으로 해제한다. 로그아웃 전에 호출한다. "
        "등록되어 있지 않은 fid를 보내도 멱등하게 204를 반환한다."
    ),
)
async def unregister_device(
    fid: str,
    principal: CurrentPrincipalDep,
    command_use_case: UnregisterDeviceTokenCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(
        UnregisterDeviceTokenCommand(
            user_id=principal.user_id,
            fid=fid,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _notification_response(notification: _NotificationResult) -> NotificationResponse:
    return NotificationResponse(
        notificationId=notification.notification_id,
        kind=notification.kind,
        message=notification.message,
        targetType=notification.target_type,
        targetId=notification.target_id,
        createdAt=notification.created_at,
        readAt=notification.read_at,
    )

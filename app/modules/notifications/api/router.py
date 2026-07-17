from datetime import datetime
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.http.auth import CurrentPrincipalDep
from app.core.http.responses import ApiErrorData, CommonResponse, CursorPaginationResponse
from app.modules.notifications.api.schemas import (
    NotificationListQuery,
    NotificationListResponse,
    NotificationResponse,
    NotificationSettingsResponse,
    RegisterDeviceRequest,
    UpdateNotificationSettingsRequest,
)
from app.modules.notifications.application.commands.delete_notification.command import (
    DeleteNotificationCommand,
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
    DeleteNotificationCommandUseCaseDep,
    GetNotificationSettingsQueryUseCaseDep,
    ListNotificationsQueryUseCaseDep,
    MarkNotificationReadCommandUseCaseDep,
    RegisterDeviceTokenCommandUseCaseDep,
    UnregisterDeviceTokenCommandUseCaseDep,
    UpdateNotificationSettingsCommandUseCaseDep,
)
from app.modules.notifications.domain.value_objects import (
    NotificationCategory,
    NotificationMessageType,
)


class _NotificationResult(Protocol):
    @property
    def notification_id(self) -> UUID: ...

    @property
    def category(self) -> NotificationCategory: ...

    @property
    def message_type(self) -> NotificationMessageType: ...

    @property
    def kind(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def message(self) -> str: ...

    @property
    def resource_type(self) -> str | None: ...

    @property
    def resource_id(self) -> UUID | None: ...

    @property
    def metadata(self) -> dict[str, str]: ...

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
    description="현재 사용자에게 생성된 앱 알림 목록을 최신순으로 반환한다.",
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


@router.delete(
    "/notifications/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": CommonResponse[ApiErrorData],
            "description": "알림을 찾을 수 없음",
        },
    },
    summary="알림 삭제",
    description="현재 사용자가 소유한 알림을 삭제한다. 성공하면 본문 없이 204를 반환한다.",
)
async def delete_notification(
    notification_id: UUID,
    principal: CurrentPrincipalDep,
    command_use_case: DeleteNotificationCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(
        DeleteNotificationCommand(
            user_id=principal.user_id,
            notification_id=notification_id,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/notifications/devices",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="FCM 디바이스 등록",
    description=(
        "로그인한 사용자의 디바이스를 FCM registration token으로 등록한다. "
        "같은 token을 다시 등록하면 플랫폼과 갱신 시각을 덮어쓰는 멱등 upsert이며, "
        "같은 token이 다른 사용자에게 등록되어 있었다면 이번 사용자 소유로 이전된다. "
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
            token=request.token,
            platform=request.platform,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/notifications/devices/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="FCM 디바이스 해제",
    description=(
        "로그인한 사용자의 디바이스 등록을 FCM registration token 기준으로 해제한다. "
        "로그아웃 전에 호출한다. 등록되어 있지 않은 token을 보내도 멱등하게 204를 반환한다."
    ),
)
async def unregister_device(
    token: str,
    principal: CurrentPrincipalDep,
    command_use_case: UnregisterDeviceTokenCommandUseCaseDep,
) -> Response:
    await command_use_case.execute(
        UnregisterDeviceTokenCommand(
            user_id=principal.user_id,
            token=token,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _notification_response(notification: _NotificationResult) -> NotificationResponse:
    return NotificationResponse(
        notificationId=notification.notification_id,
        category=notification.category,
        messageType=notification.message_type,
        kind=notification.kind,
        title=notification.title,
        message=notification.message,
        resourceType=notification.resource_type,
        resourceId=notification.resource_id,
        metadata=notification.metadata,
        createdAt=notification.created_at,
        readAt=notification.read_at,
    )

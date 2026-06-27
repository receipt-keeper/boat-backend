from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.notifications.api.schemas import (
    NotificationListResponse,
    NotificationResponse,
    NotificationSettingsResponse,
    UpdateNotificationSettingsRequest,
)
from app.modules.notifications.mock import SAMPLE_NOTIFICATIONS, notification_with_read_state

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
async def list_notifications() -> CommonResponse[NotificationListResponse]:
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=NotificationListResponse(notifications=list(SAMPLE_NOTIFICATIONS)),
    )


@router.patch(
    "/notifications/settings",
    response_model=CommonResponse[NotificationSettingsResponse],
    summary="알림 설정 수정",
    description="푸시 알림과 마케팅 알림 수신 여부를 수정한다. 보내지 않은 값은 그대로 둔다.",
)
async def update_notification_settings(
    request: UpdateNotificationSettingsRequest,
) -> CommonResponse[NotificationSettingsResponse]:
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=NotificationSettingsResponse(
            pushEnabled=request.push_enabled if request.push_enabled is not None else True,
            marketingConsent=(
                request.marketing_consent if request.marketing_consent is not None else False
            ),
        ),
    )


@router.get(
    "/notifications/settings",
    response_model=CommonResponse[NotificationSettingsResponse],
    summary="알림 설정 조회",
    description="푸시 알림과 마케팅 알림 수신 여부를 반환한다.",
)
async def get_notification_settings() -> CommonResponse[NotificationSettingsResponse]:
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=NotificationSettingsResponse(pushEnabled=True, marketingConsent=False),
    )


@router.patch(
    "/notifications/{notification_id}",
    response_model=CommonResponse[NotificationResponse],
    summary="알림 상태 수정",
    description="알림을 읽은 상태로 바꾸고 변경된 알림 정보를 반환한다.",
)
async def update_notification(
    notification_id: UUID,
) -> CommonResponse[NotificationResponse]:
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=notification_with_read_state(notification_id=notification_id, read_at=_now()),
    )


def _now() -> datetime:
    return datetime.now(UTC)

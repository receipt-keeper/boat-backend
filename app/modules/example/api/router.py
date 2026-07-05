from typing import Annotated, Final

from fastapi import APIRouter, Depends, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.auth.api.security import CurrentPrincipalDep
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.dependencies import GrantCreditCommandUseCaseDep
from app.modules.credits.domain import CreditAmount, CreditReason, FeatureKey
from app.modules.example.api.schemas import (
    OcrTestCreditGrantResponse,
    TestPushRequest,
    TestPushResponse,
)
from app.modules.notifications.application.commands.create_notification.command import (
    CreateNotificationCommand,
)
from app.modules.notifications.application.commands.create_notification.use_case import (
    CreateNotificationCommandUseCase,
)
from app.modules.notifications.application.ports.push_sender import (
    PushMessage,
    PushSender,
    PushSendReport,
)
from app.modules.notifications.application.ports.push_token_repository import (
    PushTokenRepository,
)
from app.modules.notifications.dependencies import (
    get_push_sender,
    get_push_token_repository,
    get_test_notification_create_use_case,
)
from app.modules.notifications.domain.value_objects import NotificationMessageType

_FORCED_SERVER_ERROR_MESSAGE: Final = "테스트용 서버 오류를 강제로 발생시켰습니다."
_OCR_TEST_CREDIT_GRANT_COUNT: Final = 5
_OCR_TEST_CREDIT_GRANTED_EXAMPLE = {
    "success": True,
    "status": status.HTTP_201_CREATED,
    "data": {
        "featureKey": "ocr",
        "reason": "eventOcrAllowance",
        "grantedCount": _OCR_TEST_CREDIT_GRANT_COUNT,
    },
}

router = APIRouter(
    prefix="/example",
    tags=["example"],
)


@router.get(
    "/server-error",
    response_model=CommonResponse[ApiErrorData],
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    summary="테스트용 500 오류 발생",
    description="클라이언트의 서버 오류 처리 확인을 위해 500 응답을 강제로 발생시킨다.",
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": CommonResponse[ApiErrorData],
            "description": "서버 내부 오류 강제 발생",
        },
    },
)
async def force_server_error() -> CommonResponse[ApiErrorData]:
    raise RuntimeError(_FORCED_SERVER_ERROR_MESSAGE)


@router.post(
    "/ocr-test-credits",
    response_model=CommonResponse[OcrTestCreditGrantResponse],
    status_code=status.HTTP_201_CREATED,
    summary="임시 OCR 테스트 크레딧 발급",
    description=(
        "앱 OCR 연동 테스트를 위해 인증된 현재 사용자에게 OCR 크레딧 5회를 임시 지급한다. "
        "정식 충전/이벤트 지급 API가 아니라 example 모듈의 테스트 보조 API다."
    ),
    responses={
        status.HTTP_201_CREATED: {
            "description": "OCR 테스트 크레딧 발급 성공",
            "content": {"application/json": {"example": _OCR_TEST_CREDIT_GRANTED_EXAMPLE}},
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": CommonResponse[ApiErrorData],
            "description": "인증 실패",
        },
    },
)
async def grant_ocr_test_credits(
    principal: CurrentPrincipalDep,
    use_case: GrantCreditCommandUseCaseDep,
) -> CommonResponse[OcrTestCreditGrantResponse]:
    await use_case.execute(
        GrantCreditCommand(
            user_id=principal.user_id,
            amount=CreditAmount(
                value=_OCR_TEST_CREDIT_GRANT_COUNT,
                field_name="amount",
            ),
            reason=CreditReason.EVENT_OCR_ALLOWANCE,
        )
    )
    return CommonResponse(
        success=True,
        status=status.HTTP_201_CREATED,
        data=OcrTestCreditGrantResponse(
            featureKey=FeatureKey.OCR,
            reason=CreditReason.EVENT_OCR_ALLOWANCE,
            grantedCount=_OCR_TEST_CREDIT_GRANT_COUNT,
        ),
    )


@router.post(
    "/push",
    response_model=CommonResponse[TestPushResponse],
    summary="테스트 푸시 발송",
    description=(
        "앱 푸시 연동 확인을 위해 로그인한 사용자의 등록된 모든 디바이스로 테스트 푸시를 "
        "즉시 발송한다. 알림 레코드를 생성해 알림 목록 조회 API에서 확인할 수 있으며, "
        "알림 수신 설정은 확인하지 않는 example 모듈의 테스트 보조 API다. "
        "발송 실패 시 외부 서비스 오류로 응답한다."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": CommonResponse[ApiErrorData],
            "description": "인증 실패",
        },
    },
)
async def send_test_push(
    request: TestPushRequest,
    principal: CurrentPrincipalDep,
    push_token_repository: Annotated[PushTokenRepository, Depends(get_push_token_repository)],
    push_sender: Annotated[PushSender, Depends(get_push_sender)],
    notification_create_use_case: Annotated[
        CreateNotificationCommandUseCase,
        Depends(get_test_notification_create_use_case),
    ],
) -> CommonResponse[TestPushResponse]:
    notification_result = await notification_create_use_case.execute(
        CreateNotificationCommand(
            user_id=principal.user_id,
            message_type=NotificationMessageType.TRANSACTIONAL,
            kind="test",
            title=request.title,
            message=request.body,
        )
    )
    tokens = await push_token_repository.list_by_user(user_id=principal.user_id)
    report = PushSendReport()
    if tokens:
        report = await push_sender.send(
            tokens=tokens,
            message=PushMessage(
                title=request.title,
                body=request.body,
                data={"test": "true"},
            ),
        )
    return CommonResponse(
        success=True,
        status=status.HTTP_200_OK,
        data=TestPushResponse(
            notificationId=notification_result.notification_id,
            targetedDeviceCount=len(tokens),
            invalidDeviceCount=len(report.invalid_tokens),
        ),
    )

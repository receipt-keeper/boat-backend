from typing import Final

from fastapi import APIRouter, status

from app.core.http.responses import ApiErrorData, CommonResponse
from app.modules.auth.api.security import CurrentPrincipalDep
from app.modules.credits.application.commands.grant_credit.command import GrantCreditCommand
from app.modules.credits.dependencies import GrantCreditCommandUseCaseDep
from app.modules.credits.domain import CreditAmount, CreditReason, FeatureKey
from app.modules.example.api.schemas import OcrTestCreditGrantResponse

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

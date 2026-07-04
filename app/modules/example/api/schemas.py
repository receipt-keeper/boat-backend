from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel
from app.modules.credits.domain import CreditReason, FeatureKey


class OcrTestCreditGrantResponse(AppBaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "featureKey": "ocr",
                    "reason": "eventOcrAllowance",
                    "grantedCount": 5,
                }
            ]
        },
    )

    feature_key: FeatureKey = Field(
        alias="featureKey",
        description="임시 테스트 크레딧이 지급된 기능.",
    )
    reason: CreditReason = Field(description="크레딧 지급 사유.")
    granted_count: int = Field(
        alias="grantedCount",
        description="이번 요청으로 지급된 OCR 테스트 크레딧 횟수.",
    )


class TestPushRequest(AppBaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "title": "테스트 알림",
                    "body": "푸시 연결 확인용 테스트 메시지입니다.",
                }
            ]
        },
    )

    title: str = Field(
        default="테스트 알림",
        description="테스트 푸시 제목.",
    )
    body: str = Field(
        default="푸시 연결 확인용 테스트 메시지입니다.",
        description="테스트 푸시 본문.",
    )


class TestPushResponse(AppBaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "targetedDeviceCount": 1,
                    "invalidDeviceCount": 0,
                }
            ]
        },
    )

    targeted_device_count: int = Field(
        alias="targetedDeviceCount",
        description="발송을 시도한 등록 디바이스 수.",
    )
    invalid_device_count: int = Field(
        alias="invalidDeviceCount",
        description="FCM이 무효 등록으로 판정한 디바이스 수.",
    )

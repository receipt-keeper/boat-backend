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

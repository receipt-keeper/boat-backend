from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel
from app.modules.usage.domain import ReceiptAnalysisUsage, UsageSnapshot


class ReceiptAnalysisUsageResponse(AppBaseModel):
    remaining_count: int = Field(alias="remainingCount", description="남은 영수증 분석 횟수.")
    can_analyze: bool = Field(
        alias="canAnalyze",
        description="영수증 분석을 바로 실행할 수 있는지 여부.",
    )

    @classmethod
    def from_domain(cls, usage: ReceiptAnalysisUsage) -> "ReceiptAnalysisUsageResponse":
        return cls(remainingCount=usage.remaining_count, canAnalyze=usage.can_analyze)


class UsageResponse(AppBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "ocr": {
                        "remainingCount": 3,
                        "canAnalyze": True,
                    }
                }
            ]
        },
    )

    receipt_analysis: ReceiptAnalysisUsageResponse = Field(
        alias="ocr",
        description="영수증 분석 횟수와 사용 가능 여부.",
    )

    @classmethod
    def from_domain(cls, usage: UsageSnapshot) -> "UsageResponse":
        return cls(ocr=ReceiptAnalysisUsageResponse.from_domain(usage.receipt_analysis))

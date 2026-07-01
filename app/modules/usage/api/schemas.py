from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel
from app.modules.usage.domain import OcrUsage, UsageSnapshot


class OcrUsageResponse(AppBaseModel):
    remaining_count: int = Field(alias="remainingCount", description="남은 OCR 기능 사용 횟수.")
    can_analyze: bool = Field(
        alias="canAnalyze",
        description="OCR 기능을 바로 사용할 수 있는지 여부.",
    )

    @classmethod
    def from_domain(cls, usage: OcrUsage) -> "OcrUsageResponse":
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

    ocr: OcrUsageResponse = Field(
        alias="ocr",
        description="OCR 기능 사용 가능 여부와 남은 OCR 횟수.",
    )

    @classmethod
    def from_domain(cls, usage: UsageSnapshot) -> "UsageResponse":
        return cls(ocr=OcrUsageResponse.from_domain(usage.ocr))

from enum import StrEnum


class CreditReason(StrEnum):
    MONTHLY_OCR_ALLOWANCE = "monthlyOcrAllowance"
    EVENT_OCR_ALLOWANCE = "eventOcrAllowance"
    OCR_USAGE = "ocrUsage"


class FeatureKey(StrEnum):
    OCR = "ocr"


class CreditAction(StrEnum):
    GRANT = "grant"
    USE = "use"


class CreditSourceType(StrEnum):
    PROMOTION_REDEMPTION = "promotionRedemption"
    MONTHLY_ALLOWANCE = "monthlyAllowance"
    OCR_ANALYSIS = "ocrAnalysis"

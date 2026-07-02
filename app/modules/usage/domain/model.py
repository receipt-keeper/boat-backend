from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OcrUsage:
    remaining_count: int
    can_analyze: bool


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    ocr: OcrUsage

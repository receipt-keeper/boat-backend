from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReceiptAnalysisUsage:
    remaining_count: int
    can_analyze: bool


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    receipt_analysis: ReceiptAnalysisUsage

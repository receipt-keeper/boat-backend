from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CreditReason(StrEnum):
    QUIZ_REWARD = "quizReward"
    RECEIPT_ANALYSIS = "receiptAnalysis"


class CreditAction(StrEnum):
    GRANT = "grant"
    USE = "use"


@dataclass(frozen=True, slots=True)
class CreditBalance:
    total_granted_count: int
    used_count: int
    remaining_count: int


@dataclass(frozen=True, slots=True)
class CreditTransaction:
    reason: CreditReason
    action: CreditAction
    amount: int
    created_at: datetime

from datetime import datetime
from typing import Final

from app.modules.credits.domain import (
    CreditAction,
    CreditBalance,
    CreditReason,
    CreditTransaction,
)

SAMPLE_CREDIT_BALANCE: Final = CreditBalance(
    total_granted_count=10,
    used_count=7,
    remaining_count=3,
)
SAMPLE_CREDIT_TRANSACTIONS: Final[tuple[CreditTransaction, ...]] = (
    CreditTransaction(
        reason=CreditReason.QUIZ_REWARD,
        action=CreditAction.GRANT,
        amount=10,
        created_at=datetime.fromisoformat("2026-06-26T00:00:00"),
    ),
    CreditTransaction(
        reason=CreditReason.RECEIPT_ANALYSIS,
        action=CreditAction.USE,
        amount=1,
        created_at=datetime.fromisoformat("2026-06-26T09:30:00"),
    ),
)

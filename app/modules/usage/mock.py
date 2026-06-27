from typing import Final

from app.modules.usage.domain import ReceiptAnalysisUsage, UsageSnapshot

SAMPLE_USAGE: Final = UsageSnapshot(
    receipt_analysis=ReceiptAnalysisUsage(
        remaining_count=3,
        can_analyze=True,
    ),
)

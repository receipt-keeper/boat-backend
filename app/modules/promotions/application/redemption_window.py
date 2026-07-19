from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.modules.promotions.domain.model import Promotion, PromotionKind

SEOUL_TZ = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class PromotionRedemptionWindow:
    starts_at: datetime | None
    expires_at: datetime | None


def current_user_redemption_window(
    *,
    promotion: Promotion,
    at: datetime,
) -> PromotionRedemptionWindow:
    if promotion.kind != PromotionKind.REWARDED_AD:
        return PromotionRedemptionWindow(starts_at=None, expires_at=None)

    local_date = at.astimezone(SEOUL_TZ).date()
    starts_at = datetime.combine(local_date, time.min, tzinfo=SEOUL_TZ)
    return PromotionRedemptionWindow(
        starts_at=starts_at.astimezone(UTC),
        expires_at=(starts_at + timedelta(days=1)).astimezone(UTC),
    )

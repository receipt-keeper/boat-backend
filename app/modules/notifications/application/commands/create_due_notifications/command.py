from dataclasses import dataclass
from datetime import date, datetime

from app.core.domain.exceptions import ErrorDetail, ValidationError


@dataclass(frozen=True, slots=True)
class CreateDueNotificationsCommand:
    target_date: date | None
    now: datetime
    campaign_key: str | None
    dry_run: bool
    batch_size: int

    def __post_init__(self) -> None:
        details: list[ErrorDetail] = []
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            details.append(
                ErrorDetail(field="now", message="예약 알림 기준 시각이 올바르지 않습니다.")
            )
        if self.campaign_key is not None and (
            not self.campaign_key
            or self.campaign_key.strip() != self.campaign_key
            or len(self.campaign_key) > 100
        ):
            details.append(
                ErrorDetail(field="campaignKey", message="예약 알림 캠페인 키가 올바르지 않습니다.")
            )
        if self.batch_size < 1:
            details.append(
                ErrorDetail(field="batchSize", message="예약 알림 batchSize가 올바르지 않습니다.")
            )
        if details:
            raise ValidationError(details)

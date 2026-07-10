from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError

_INVALID_BATCH_SIZE = "영수증 등록 활동 후보 조회 batchSize가 올바르지 않습니다."
_INVALID_RECENT_SINCE = "영수증 등록 활동 후보 조회 recentSince가 올바르지 않습니다."


@dataclass(frozen=True, slots=True)
class GetReceiptActivityForUsersQuery:
    user_ids: tuple[UUID, ...]
    limit: int
    recent_since: datetime | None
    cursor_user_id: UUID | None = None

    def __post_init__(self) -> None:
        details: list[ErrorDetail] = []
        if self.limit < 1:
            details.append(ErrorDetail(field="batchSize", message=_INVALID_BATCH_SIZE))
        if self.recent_since is not None and (
            self.recent_since.tzinfo is None or self.recent_since.utcoffset() is None
        ):
            details.append(ErrorDetail(field="recentSince", message=_INVALID_RECENT_SINCE))
        if details:
            raise ValidationError(details)

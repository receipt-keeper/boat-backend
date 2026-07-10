from dataclasses import dataclass
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError

_INVALID_USER_IDS = "사용자 존재 여부 조회 userIds가 올바르지 않습니다."


@dataclass(frozen=True, slots=True)
class GetExistingUserIdsQuery:
    user_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        if not all(isinstance(user_id, UUID) for user_id in self.user_ids):
            raise ValidationError([ErrorDetail(field="userIds", message=_INVALID_USER_IDS)])

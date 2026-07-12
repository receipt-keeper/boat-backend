from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.core.domain.exceptions import ErrorDetail, ValidationError

_MAX_BENEFICIARY_KEY_LENGTH: Final = 80


@dataclass(frozen=True, slots=True)
class RedeemSignupPromotionCommand:
    user_id: UUID
    beneficiary_key: str

    def __post_init__(self) -> None:
        if (
            self.beneficiary_key.strip() == ""
            or len(self.beneficiary_key) > _MAX_BENEFICIARY_KEY_LENGTH
        ):
            raise ValidationError(
                [
                    ErrorDetail(
                        field="beneficiary_key",
                        message="신규 가입 프로모션 수혜자 키가 올바르지 않습니다.",
                    )
                ]
            )

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


class NotificationKind(StrEnum):
    WARRANTY_NOTICE = "warranty_notice"
    WARRANTY_WARNING = "warranty_warning"
    WARRANTY_RISK = "warranty_risk"
    WARRANTY_EXPIRED = "warranty_expired"
    REGISTRATION_PROMPT = "registration_prompt"
    CREDIT_PROMPT = "credit_prompt"


class NotificationTargetType(StrEnum):
    RECEIPT = "receipt"
    RECEIPT_UPLOAD = "receiptUpload"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class NotificationMessage(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="message", message="알림 문구가 올바르지 않습니다.")]
            )

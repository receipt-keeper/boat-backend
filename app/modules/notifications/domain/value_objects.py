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
    BENEFIT = "benefit"


class NotificationTargetType(StrEnum):
    RECEIPT = "receipt"
    RECEIPT_UPLOAD = "receiptUpload"
    NONE = "none"


class DevicePlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


@dataclass(frozen=True, slots=True)
class NotificationMessage(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="message", message="알림 문구가 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class Fid(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError([ErrorDetail(field="fid", message="FID가 올바르지 않습니다.")])

    def __repr__(self) -> str:
        # 로그/예외에 발송 식별자 원문이 노출되지 않도록 마스킹한다.
        return f"Fid(****{len(self.value)})"

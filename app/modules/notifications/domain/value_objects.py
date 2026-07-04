from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


class NotificationCategory(StrEnum):
    SERVICE = "service"
    MARKETING = "marketing"


class DevicePlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


@dataclass(frozen=True, slots=True)
class NotificationKind(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 50

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="kind", message="알림 유형이 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class NotificationTitle(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 100

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="title", message="알림 제목이 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class NotificationMessage(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="message", message="알림 문구가 올바르지 않습니다.")]
            )


@dataclass(frozen=True, slots=True)
class ResourceType(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 50

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="resourceType", message="리소스 유형이 올바르지 않습니다.")]
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

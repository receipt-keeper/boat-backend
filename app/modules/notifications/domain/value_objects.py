from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


class NotificationMessageType(StrEnum):
    TRANSACTIONAL = "transactional"
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
class NotificationMetadata(ValueObject[Mapping[str, str]]):
    MAX_KEYS: ClassVar[int] = 50
    MIN_KEY_LENGTH: ClassVar[int] = 1
    MAX_KEY_LENGTH: ClassVar[int] = 40
    MAX_VALUE_LENGTH: ClassVar[int] = 500

    def __post_init__(self) -> None:
        # 내부 복사본으로 불변을 보장한 뒤 검증한다(호출부의 dict가 이후 변경돼도 영향 없음).
        object.__setattr__(self, "value", dict(self.value))
        self.validate()

    def validate(self) -> None:
        if len(self.value) > self.MAX_KEYS:
            raise ValidationError(
                [ErrorDetail(field="metadata", message="metadata는 최대 50개 키까지 허용됩니다.")]
            )
        for key, item_value in self.value.items():
            if (
                not isinstance(key, str)
                or key.strip() != key
                or not (self.MIN_KEY_LENGTH <= len(key) <= self.MAX_KEY_LENGTH)
            ):
                raise ValidationError(
                    [
                        ErrorDetail(
                            field="metadata",
                            message="metadata 키는 1~40자이며 앞뒤 공백이 없어야 합니다.",
                        )
                    ]
                )
            if not isinstance(item_value, str) or len(item_value) > self.MAX_VALUE_LENGTH:
                raise ValidationError(
                    [
                        ErrorDetail(
                            field="metadata",
                            message="metadata 값은 문자열이며 500자를 넘을 수 없습니다.",
                        )
                    ]
                )


@dataclass(frozen=True, slots=True)
class RegistrationToken(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 512

    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="token", message="FCM 등록 토큰이 올바르지 않습니다.")]
            )

    def __repr__(self) -> str:
        # 로그/예외에 발송 식별자 원문이 노출되지 않도록 마스킹한다.
        return f"RegistrationToken(****{len(self.value)})"

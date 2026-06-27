from dataclasses import dataclass
from typing import ClassVar

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


@dataclass(frozen=True, slots=True)
class Email(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if (
            not self.value
            or self.value.strip() != self.value
            or "@" not in self.value
            or len(self.value) > self.MAX_LENGTH
        ):
            raise ValidationError(
                [
                    ErrorDetail(
                        field="email",
                        message="이메일이 올바르지 않습니다.",
                    )
                ]
            )


@dataclass(frozen=True, slots=True)
class FreeAnalysisTokensRemaining(ValueObject[int]):
    def validate(self) -> None:
        if self.value < 0:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="freeAnalysisTokensRemaining",
                        message="무료 영수증 분석 잔여 횟수는 0 이상이어야 합니다.",
                    )
                ]
            )


@dataclass(frozen=True, slots=True)
class PushPlatform(ValueObject[str]):
    ALLOWED: ClassVar[set[str]] = {"android", "ios", "web"}

    def validate(self) -> None:
        if self.value not in self.ALLOWED:
            raise ValidationError(
                [ErrorDetail(field="platform", message="푸시 플랫폼이 올바르지 않습니다.")]
            )

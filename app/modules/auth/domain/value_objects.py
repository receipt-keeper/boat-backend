from dataclasses import dataclass
from typing import ClassVar

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


@dataclass(frozen=True)
class Issuer(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 50

    def validate(self) -> None:
        if not self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="issuer", message="인증 발급자가 올바르지 않습니다.")]
            )


@dataclass(frozen=True)
class Subject(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if not self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="subject", message="외부 인증 식별자가 올바르지 않습니다.")]
            )


@dataclass(frozen=True)
class Provider(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 50

    def validate(self) -> None:
        if not self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="provider", message="로그인 제공자가 올바르지 않습니다.")]
            )


@dataclass(frozen=True)
class NormalizedEmail(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if (
            not self.value
            or self.value.strip() != self.value
            or self.value.lower() != self.value
            or "@" not in self.value
            or len(self.value) > self.MAX_LENGTH
        ):
            raise ValidationError(
                [
                    ErrorDetail(
                        field="normalizedEmail",
                        message="정규화된 이메일이 올바르지 않습니다.",
                    )
                ]
            )


@dataclass(frozen=True)
class Role(ValueObject[str]):
    ALLOWED: ClassVar[set[str]] = {"user", "admin"}

    def validate(self) -> None:
        if self.value not in self.ALLOWED:
            raise ValidationError([ErrorDetail(field="role", message="권한이 올바르지 않습니다.")])


@dataclass(frozen=True)
class TokenHash(ValueObject[str]):
    MAX_LENGTH: ClassVar[int] = 255

    def validate(self) -> None:
        if not self.value or len(self.value) > self.MAX_LENGTH:
            raise ValidationError(
                [ErrorDetail(field="tokenHash", message="토큰 해시가 올바르지 않습니다.")]
            )

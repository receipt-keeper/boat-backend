import re
from dataclasses import dataclass
from typing import ClassVar, Final

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject

PROMOTION_BENEFICIARY_KEY_PATTERN: Final = re.compile(r"v1:[0-9a-f]{64}")


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


@dataclass(frozen=True, slots=True)
class PromotionBeneficiaryHmacSecret(ValueObject[str]):
    def validate(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="promotionBeneficiaryHmacSecret",
                        message="프로모션 수혜자 HMAC 비밀값이 올바르지 않습니다.",
                    )
                ]
            )


@dataclass(frozen=True, slots=True)
class PromotionBeneficiaryKey(ValueObject[str]):
    def validate(self) -> None:
        if PROMOTION_BENEFICIARY_KEY_PATTERN.fullmatch(self.value) is None:
            raise ValidationError(
                [
                    ErrorDetail(
                        field="promotionBeneficiaryKey",
                        message="프로모션 수혜자 식별키가 올바르지 않습니다.",
                    )
                ]
            )

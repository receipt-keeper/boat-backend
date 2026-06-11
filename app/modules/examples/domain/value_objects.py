from dataclasses import dataclass
from typing import ClassVar

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.value_object import ValueObject


@dataclass(frozen=True)
class Nickname(ValueObject[str]):
    MIN_LENGTH: ClassVar[int] = 1
    MAX_LENGTH: ClassVar[int] = 64

    def validate(self) -> None:
        if not (self.MIN_LENGTH <= len(self.value) <= self.MAX_LENGTH):
            message = f"닉네임은 {self.MIN_LENGTH}자 이상 {self.MAX_LENGTH}자 이하여야 합니다."
            raise ValidationError([ErrorDetail(field="nickname", message=message)])


@dataclass(frozen=True)
class Email(ValueObject[str]):
    def validate(self) -> None:
        if "@" not in self.value or "." not in self.value.rsplit("@", maxsplit=1)[-1]:
            raise ValidationError(
                [ErrorDetail(field="email", message="이메일 형식이 올바르지 않습니다.")]
            )


@dataclass(frozen=True)
class Password(ValueObject[str]):
    MIN_LENGTH: ClassVar[int] = 8

    def validate(self) -> None:
        if len(self.value) < self.MIN_LENGTH:
            message = f"비밀번호는 {self.MIN_LENGTH}자 이상이어야 합니다."
            raise ValidationError([ErrorDetail(field="password", message=message)])

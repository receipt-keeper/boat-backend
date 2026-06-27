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

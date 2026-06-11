from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ValueObject[ValueT](ABC):
    value: ValueT

    def __post_init__(self) -> None:
        self.validate()

    @abstractmethod
    def validate(self) -> None:
        """값 불변식을 검증하고 위반 시 도메인 예외를 발생시킨다."""

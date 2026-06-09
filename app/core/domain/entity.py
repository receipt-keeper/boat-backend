from dataclasses import dataclass
from typing import TypeVar

IdT = TypeVar("IdT")


@dataclass(eq=False)
class Entity[IdT]:
    id: IdT

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return False
        return self.id == other.id and type(self) is type(other)

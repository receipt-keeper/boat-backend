from dataclasses import dataclass


@dataclass(eq=False)
class Entity[IdT]:
    id: IdT

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return False
        return self.id == other.id and type(self) is type(other)

    def __hash__(self) -> int:
        return hash((type(self), self.id))

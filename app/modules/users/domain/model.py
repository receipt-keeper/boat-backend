from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.domain.entity import Entity


@dataclass(eq=False)
class User(Entity[UUID]):
    name: str | None
    email: str | None
    nickname: str | None = None

    @classmethod
    def create(
        cls,
        *,
        name: str | None,
        email: str | None,
        user_id: UUID | None = None,
        nickname: str | None = None,
    ) -> "User":
        return cls(
            id=user_id or uuid4(),
            name=name,
            email=email,
            nickname=nickname,
        )

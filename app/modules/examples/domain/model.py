from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.domain.entity import Entity
from app.core.domain.validation import Notification
from app.modules.examples.domain.value_objects import Email, Nickname, Password


@dataclass(eq=False)
class ExampleUser(Entity[UUID]):
    nickname: Nickname
    email: Email

    @classmethod
    def create(cls, *, nickname: str, email: str, password: str) -> "ExampleUser":
        # password는 아직 영속화하지 않는 예시 — 생성 규칙상 검증만 수행한다
        notification = Notification()
        new_nickname = notification.collect(lambda: Nickname(nickname))
        new_email = notification.collect(lambda: Email(email))
        notification.collect(lambda: Password(password))
        notification.raise_if_any()

        return cls(
            id=uuid4(),
            nickname=new_nickname,
            email=new_email,
        )

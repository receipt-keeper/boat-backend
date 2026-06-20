from app.modules.users.domain.model import User as DomainUser
from app.modules.users.infrastructure.persistence import orm


def user_to_domain(record: orm.User) -> DomainUser:
    return DomainUser.create(
        user_id=record.id,
        name=record.name,
        email=record.email,
        nickname=record.nickname,
    )


def user_to_record(user: DomainUser) -> orm.User:
    return orm.User(
        id=user.id,
        name=user.name,
        nickname=user.nickname,
        email=user.email,
    )

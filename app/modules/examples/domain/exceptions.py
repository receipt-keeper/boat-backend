from uuid import UUID

from app.core.domain.exceptions import NotFoundError


class ExampleUserNotFoundError(NotFoundError):
    def __init__(self, example_user_id: UUID) -> None:
        super().__init__("예시 사용자를 찾을 수 없습니다.")
        self.example_user_id = example_user_id

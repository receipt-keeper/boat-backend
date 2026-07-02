from app.core.domain.exceptions import ConflictError


class InsufficientCreditError(ConflictError):
    def __init__(self) -> None:
        super().__init__("사용 가능한 크레딧이 부족합니다.")

    @property
    def code(self) -> str:
        return "INSUFFICIENT_CREDIT"

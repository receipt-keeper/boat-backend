from app.core.domain.exceptions import ConflictError, NotFoundError


class PromotionNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("프로모션을 찾을 수 없습니다.")


class PromotionCodeNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("프로모션 코드를 찾을 수 없습니다.")


class PromotionRedemptionConflictError(ConflictError):
    def __init__(self, message: str = "프로모션을 사용할 수 없습니다.") -> None:
        super().__init__(message)

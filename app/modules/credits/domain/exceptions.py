from app.core.domain.exceptions import ConflictError


class InsufficientCreditError(ConflictError):
    def __init__(self) -> None:
        super().__init__("사용 가능한 크레딧이 부족합니다.")

    @property
    def code(self) -> str:
        return "INSUFFICIENT_CREDIT"


class CreditBalancePreconditionError(ConflictError):
    def __init__(self) -> None:
        super().__init__("현재 크레딧 잔액이 지급 조건과 일치하지 않습니다.")

    @property
    def code(self) -> str:
        return "CREDIT_BALANCE_PRECONDITION_FAILED"

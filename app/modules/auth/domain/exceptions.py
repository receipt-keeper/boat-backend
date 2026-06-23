from app.core.domain.exceptions import DomainError


class AuthenticationError(DomainError):
    """인증 실패 — credential 누락, 만료, 위조, 외부 token 검증 실패를 표현한다."""

    def __init__(self, message: str = "인증 정보가 올바르지 않습니다.") -> None:
        super().__init__(message)


class AuthenticationRequiredError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("인증 정보가 필요합니다.")


class AuthorizationError(DomainError):
    """인가 실패 — 인증된 principal이 필요한 권한을 갖지 못한 경우를 표현한다."""

    def __init__(self, message: str = "접근 권한이 없습니다.") -> None:
        super().__init__(message)

from app.core.domain.exceptions import ConflictError, DomainError, NotFoundError


class AuthenticationError(DomainError):
    """인증 실패 — credential 누락, 만료, 위조, 외부 token 검증 실패를 표현한다."""

    def __init__(self, message: str = "인증 정보가 올바르지 않습니다.") -> None:
        super().__init__(message)


class AuthenticationRequiredError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("인증 정보가 필요합니다.")


class UserNotRegisteredError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("가입되지 않은 사용자입니다.")

    @property
    def code(self) -> str:
        return "USER_NOT_REGISTERED"


class UserAlreadyExistsError(ConflictError):
    def __init__(self) -> None:
        super().__init__("이미 가입된 사용자입니다.")

    @property
    def code(self) -> str:
        return "USER_ALREADY_EXISTS"


class AuthorizationError(DomainError):
    """인가 실패 — 인증된 principal이 필요한 권한을 갖지 못한 경우를 표현한다."""

    def __init__(self, message: str = "접근 권한이 없습니다.") -> None:
        super().__init__(message)

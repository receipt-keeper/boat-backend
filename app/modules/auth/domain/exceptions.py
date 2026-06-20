from app.core.domain.exceptions import DomainError


class AuthenticationError(DomainError):
    """인증 실패 — credential 누락, 만료, 위조, 외부 token 검증 실패를 표현한다."""


class AuthorizationError(DomainError):
    """인가 실패 — 인증된 principal이 필요한 권한을 갖지 못한 경우를 표현한다."""

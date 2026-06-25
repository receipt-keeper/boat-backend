from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDetail:
    field: str
    message: str


class DomainError(Exception):
    """도메인 에러의 루트 — 의미(메시지·맥락)만 표현하고 HTTP 등 표현 방식은 모른다.

    HTTP 상태 코드 매핑은 edge(app/core/http/exception_handlers.py)가
    예외 카테고리(ValidationError, NotFoundError, ...) 기준으로 수행한다.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ValidationError(DomainError):
    """필드 검증 실패 — 실패한 모든 필드의 ErrorDetail을 담는다 (최소 1개).

    message는 응답 전체의 대표 요약이고, 필드별 메시지는 details(errors[])가 전담한다.
    필드별 메시지는 규칙을 소유한 값 객체가 직접 정의한다.
    """

    def __init__(self, details: list[ErrorDetail]) -> None:
        self.details = details
        super().__init__("입력값이 올바르지 않습니다.")


class NotFoundError(DomainError):
    """대상 부재 — 모듈 예외가 이를 상속하고 발생 맥락(식별자 등)을 보유한다."""


class ConflictError(DomainError):
    pass


class ExternalServiceError(DomainError):
    """외부 의존 서비스 장애 — 사용자가 수정할 수 없는 일시적 실패를 표현한다."""

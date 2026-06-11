from collections.abc import Callable

from app.core.domain.exceptions import ErrorDetail, ValidationError


class Notification:
    """검증 실패를 누적했다가 한 번에 보고하는 Notification 패턴 구현.

    값 객체 생성을 collect()로 감싸면 개별 ValidationError가 누적되고,
    raise_if_any()가 누적된 모든 ErrorDetail을 담은 ValidationError 하나를 던진다.
    """

    def __init__(self) -> None:
        self._details: list[ErrorDetail] = []

    def collect[ValueT](self, factory: Callable[[], ValueT]) -> ValueT:
        """factory 실행 값을 반환하고, 검증 실패는 누적한다.

        실패 시 내부적으로 None을 반환하므로, 반환값은 반드시 raise_if_any() 호출
        이후에만 사용해야 한다 (실패가 있었다면 raise_if_any가 던져서 도달 불가).
        """
        try:
            return factory()
        except ValidationError as error:
            self._details.extend(error.details)
            return None  # type: ignore[return-value]  # raise_if_any() 이전 사용 금지 계약

    def raise_if_any(self) -> None:
        if self._details:
            raise ValidationError(self._details)

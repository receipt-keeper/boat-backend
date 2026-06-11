import pytest

from app.core.domain.exceptions import ErrorDetail, ValidationError
from app.core.domain.validation import Notification


def _fail(field: str) -> str:
    raise ValidationError([ErrorDetail(field=field, message=f"{field} 오류")])


def test_collect_returns_value_on_success() -> None:
    notification = Notification()

    assert notification.collect(lambda: "ok") == "ok"


def test_collect_accumulates_all_failures_and_raises_once() -> None:
    notification = Notification()

    notification.collect(lambda: _fail("a"))
    notification.collect(lambda: "ok")
    notification.collect(lambda: _fail("b"))

    with pytest.raises(ValidationError) as exc_info:
        notification.raise_if_any()

    assert exc_info.value.details == [
        ErrorDetail(field="a", message="a 오류"),
        ErrorDetail(field="b", message="b 오류"),
    ]


def test_raise_if_any_is_noop_without_failures() -> None:
    notification = Notification()

    notification.collect(lambda: "ok")
    notification.raise_if_any()

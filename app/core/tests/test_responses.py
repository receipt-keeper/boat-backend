from pydantic_core import ErrorDetails

from app.core.http.responses import FieldError


def _error_details(**overrides: object) -> ErrorDetails:
    details: ErrorDetails = {
        "type": "value_error",
        "loc": ("body", "email"),
        "msg": "Value error, invalid",
        "input": "invalid",
    }
    details.update(overrides)  # type: ignore[typeddict-item]
    return details


def test_from_pydantic_error_strips_request_location_prefix() -> None:
    field_error = FieldError.from_pydantic_error(_error_details(loc=("body", "profile", "email")))

    assert field_error.field == "profile.email"


def test_from_pydantic_error_keeps_field_named_like_location_prefix() -> None:
    field_error = FieldError.from_pydantic_error(_error_details(loc=("body", "items", 0, "path")))

    assert field_error.field == "items.0.path"


def test_from_pydantic_error_uses_default_message_without_context() -> None:
    field_error = FieldError.from_pydantic_error(_error_details(msg="Field required"))

    assert field_error.message == "Field required"


def test_from_pydantic_error_unwraps_string_context() -> None:
    field_error = FieldError.from_pydantic_error(
        _error_details(ctx={"error": "이메일 형식이 올바르지 않습니다."})
    )

    assert field_error.message == "이메일 형식이 올바르지 않습니다."


def test_from_pydantic_error_unwraps_exception_context() -> None:
    field_error = FieldError.from_pydantic_error(
        _error_details(ctx={"error": ValueError("비밀번호는 8자 이상이어야 합니다.")})
    )

    assert field_error.message == "비밀번호는 8자 이상이어야 합니다."

import dataclasses
from datetime import datetime
from enum import StrEnum
from typing import Any, get_type_hints
from uuid import UUID

from app.core.domain.events import DomainEvent


class UnregisteredEventTypeError(Exception):
    """event_type 문자열이 EventTypeRegistry에 등록되지 않은 경우 발생한다."""

    def __init__(self, event_type: str) -> None:
        self.event_type = event_type
        super().__init__(f"등록되지 않은 이벤트 타입입니다: {event_type!r}")


class EventTypeRegistry:
    """이벤트 클래스명 -> DomainEvent 서브클래스 명시 등록소.

    outbox 직렬화는 클래스의 import 경로 대신 클래스명 문자열을 저장하므로,
    역직렬화 시에는 이 레지스트리에 명시적으로 등록된 타입만 복원할 수 있다.
    """

    def __init__(self) -> None:
        self._types: dict[str, type[DomainEvent]] = {}

    def register(self, event_class: type[DomainEvent]) -> None:
        self._types[event_class.__name__] = event_class

    def merge(self, other: "EventTypeRegistry") -> None:
        """다른 레지스트리에 등록된 타입을 이 레지스트리로 흡수한다.

        여러 모듈의 `build_<module>_event_registry()` 결과를 단일 레지스트리로
        합성할 때 쓴다(예: main.py의 outbox relay 조립 지점). 동일한 클래스명이
        이미 등록되어 있으면 `other`의 등록으로 덮어쓴다.
        """
        self._types.update(other._types)

    def resolve(self, event_type: str) -> type[DomainEvent]:
        try:
            return self._types[event_type]
        except KeyError:
            raise UnregisteredEventTypeError(event_type) from None


def _encode_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    return value


def _decode_value(field_type: Any, value: Any) -> Any:
    if value is None:
        return None
    # `X | None` 애노테이션에서 실제 타입을 뽑아낸다.
    underlying_type = field_type
    if hasattr(field_type, "__args__"):
        non_none_args = [arg for arg in field_type.__args__ if arg is not type(None)]
        if len(non_none_args) == 1:
            underlying_type = non_none_args[0]

    if underlying_type is UUID:
        return UUID(value)
    if underlying_type is datetime:
        return datetime.fromisoformat(value)
    if isinstance(underlying_type, type) and issubclass(underlying_type, StrEnum):
        return underlying_type(value)
    return value


def serialize_event(event: DomainEvent) -> tuple[str, dict[str, Any]]:
    """DomainEvent를 (event_type 클래스명, JSON 호환 payload)로 직렬화한다."""
    payload = {
        field.name: _encode_value(getattr(event, field.name)) for field in dataclasses.fields(event)
    }
    return type(event).__name__, payload


def deserialize_event(
    registry: EventTypeRegistry,
    event_type: str,
    payload: dict[str, Any],
) -> DomainEvent:
    """event_type 문자열과 payload로 DomainEvent를 복원한다.

    미등록 event_type은 `UnregisteredEventTypeError`로 명시적으로 실패한다.
    """
    event_class = registry.resolve(event_type)
    type_hints = get_type_hints(event_class)

    kwargs = {
        field.name: _decode_value(type_hints[field.name], payload[field.name])
        for field in dataclasses.fields(event_class)
    }
    return event_class(**kwargs)

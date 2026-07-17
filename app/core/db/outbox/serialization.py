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


class ConflictingEventTypeError(Exception):
    """서로 다른 이벤트 클래스가 같은 클래스명으로 병합될 때 발생한다."""

    def __init__(
        self,
        *,
        event_type: str,
        existing: type[DomainEvent],
        incoming: type[DomainEvent],
    ) -> None:
        self.event_type = event_type
        self.existing = existing
        self.incoming = incoming
        super().__init__(
            f"이벤트 타입 이름이 충돌합니다: {event_type!r} ({existing!r} vs {incoming!r})"
        )


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
        합성할 때 쓴다(예: main.py의 outbox relay 조립 지점). 같은 클래스의
        재등록은 멱등으로 허용하되, 서로 다른 클래스가 같은 이름으로 충돌하면
        outbox row가 엉뚱한 타입으로 복원되는 정합성 사고이므로 조립 시점에
        즉시 실패시킨다.
        """
        for name, event_class in other._types.items():
            existing = self._types.get(name)
            if existing is not None and existing is not event_class:
                raise ConflictingEventTypeError(
                    event_type=name,
                    existing=existing,
                    incoming=event_class,
                )
            self._types[name] = event_class

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


def _payload_value(field: dataclasses.Field[Any], payload: dict[str, Any]) -> Any:
    if field.name in payload:
        return payload[field.name]
    if field.default is not dataclasses.MISSING:
        return field.default
    if field.default_factory is not dataclasses.MISSING:
        return field.default_factory()
    raise KeyError(field.name)


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
        field.name: _decode_value(type_hints[field.name], _payload_value(field, payload))
        for field in dataclasses.fields(event_class)
    }
    return event_class(**kwargs)

from dataclasses import dataclass, field

from app.core.domain.events import DomainEvent


@dataclass(eq=False)
class Entity[IdT]:
    id: IdT
    _domain_events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def record_event(self, event: DomainEvent) -> None:
        self._domain_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return False
        return self.id == other.id and type(self) is type(other)

    def __hash__(self) -> int:
        return hash((type(self), self.id))

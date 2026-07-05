from dataclasses import dataclass

import pytest

from app.core.domain.entity import AggregateRoot, Entity
from app.core.domain.events import DomainEvent


@dataclass(eq=False)
class StubEntity(Entity[int]):
    name: str


@dataclass(eq=False)
class OtherEntity(Entity[int]):
    name: str


@dataclass(eq=False)
class StubAggregateRoot(AggregateRoot[int]):
    name: str


def test_entities_with_same_id_are_equal_and_hash_equal() -> None:
    first = StubEntity(id=1, name="a")
    second = StubEntity(id=1, name="b")

    assert first == second
    assert hash(first) == hash(second)


def test_entities_with_same_id_but_different_type_are_not_equal() -> None:
    assert StubEntity(id=1, name="a") != OtherEntity(id=1, name="a")


def test_entity_is_usable_in_sets() -> None:
    entity = StubEntity(id=1, name="a")

    assert entity in {entity}


def test_plain_entity_has_no_record_event() -> None:
    entity = StubEntity(id=1, name="a")

    assert not hasattr(entity, "record_event")
    with pytest.raises(AttributeError):
        entity.record_event(DomainEvent())  # type: ignore[attr-defined]


def test_aggregate_root_records_and_pulls_domain_events() -> None:
    root = StubAggregateRoot(id=1, name="a")
    event = DomainEvent()

    root.record_event(event)

    assert root.pull_events() == [event]
    assert root.pull_events() == []


def test_aggregate_root_preserves_entity_identity_semantics() -> None:
    first = StubAggregateRoot(id=1, name="a")
    second = StubAggregateRoot(id=1, name="b")

    assert first == second
    assert hash(first) == hash(second)
    assert isinstance(first, Entity)

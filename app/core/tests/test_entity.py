from dataclasses import dataclass

from app.core.domain.entity import Entity


@dataclass(eq=False)
class StubEntity(Entity[int]):
    name: str


@dataclass(eq=False)
class OtherEntity(Entity[int]):
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

from datetime import UTC
from uuid import UUID

from app.core.domain.events import DomainEvent


def test_domain_event_has_default_identity_timestamp_and_version() -> None:
    event = DomainEvent()

    assert isinstance(event.event_id, UUID)
    assert event.occurred_at.tzinfo == UTC
    assert event.event_version == 1

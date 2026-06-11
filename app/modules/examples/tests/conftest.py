from collections.abc import Callable, Iterator

import pytest

from app.main import app
from app.modules.examples.dependencies import get_example_user_service


@pytest.fixture
def override_example_user_service() -> Iterator[Callable[[object], None]]:
    def _override(service: object) -> None:
        app.dependency_overrides[get_example_user_service] = lambda: service

    yield _override
    app.dependency_overrides.clear()

from collections.abc import Callable, Iterator

import pytest

from app.main import app
from app.modules.ocr.dependencies import get_receipt_ocr_client
from app.modules.ocr.infrastructure.receipt_ocr_client import (
    ReceiptOcrClient,
    ReceiptOcrClientProtocol,
)


@pytest.fixture(autouse=True)
def use_contract_receipt_ocr_client() -> Iterator[None]:
    app.dependency_overrides[get_receipt_ocr_client] = lambda: ReceiptOcrClient()

    yield
    app.dependency_overrides.pop(get_receipt_ocr_client, None)


@pytest.fixture
def override_receipt_ocr_client() -> Iterator[Callable[[ReceiptOcrClientProtocol], None]]:
    def _override(ocr_client: ReceiptOcrClientProtocol) -> None:
        app.dependency_overrides[get_receipt_ocr_client] = lambda: ocr_client

    yield _override
    app.dependency_overrides.pop(get_receipt_ocr_client, None)

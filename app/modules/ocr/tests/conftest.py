from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from uuid import UUID

import pytest
from fastapi import Request

from app.core.http.auth import get_current_principal, set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.credits.application.commands.use_credit.command import UseCreditCommand
from app.modules.credits.dependencies import (
    get_finalize_credit_usage_command_use_case,
    get_reserve_credit_command_use_case,
    get_unit_of_work,
)
from app.modules.ocr.application.ports.receipt_ocr_client import ReceiptOcrClientPort
from app.modules.ocr.dependencies import get_receipt_ocr_client
from app.modules.ocr.infrastructure.receipt_ocr_client import ReceiptOcrClient
from tests.support.unit_of_work import FakeUnitOfWork


@dataclass(slots=True)
class RecordingUseCreditCommandUseCase:
    commands: list[UseCreditCommand] = field(default_factory=list)

    async def execute(self, command: UseCreditCommand) -> None:
        self.commands.append(command)


@pytest.fixture(autouse=True)
def use_authenticated_principal() -> Iterator[None]:
    async def authenticate(request: Request) -> AuthenticatedPrincipal:
        principal = AuthenticatedPrincipal(
            user_id=UUID("00000000-0000-0000-0000-000000000301"),
            credentials_id=UUID("00000000-0000-0000-0000-000000000302"),
            session_id=UUID("00000000-0000-0000-0000-000000000303"),
            role="user",
        )
        set_current_principal(request, principal)
        return principal

    app.dependency_overrides[authenticate_current_principal] = authenticate
    app.dependency_overrides[get_current_principal] = authenticate

    yield
    app.dependency_overrides.pop(authenticate_current_principal, None)
    app.dependency_overrides.pop(get_current_principal, None)


@pytest.fixture(autouse=True)
def use_recording_credit_reservation_command_use_case() -> Iterator[
    RecordingUseCreditCommandUseCase
]:
    recorder = RecordingUseCreditCommandUseCase()
    app.dependency_overrides[get_reserve_credit_command_use_case] = lambda: recorder

    yield recorder
    app.dependency_overrides.pop(get_reserve_credit_command_use_case, None)


@pytest.fixture(autouse=True)
def use_recording_credit_command_use_case() -> Iterator[RecordingUseCreditCommandUseCase]:
    recorder = RecordingUseCreditCommandUseCase()
    app.dependency_overrides[get_finalize_credit_usage_command_use_case] = lambda: recorder

    yield recorder
    app.dependency_overrides.pop(get_finalize_credit_usage_command_use_case, None)


@pytest.fixture(autouse=True)
def use_recording_unit_of_work() -> Iterator[FakeUnitOfWork]:
    unit_of_work = FakeUnitOfWork()
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work

    yield unit_of_work
    app.dependency_overrides.pop(get_unit_of_work, None)


@pytest.fixture(autouse=True)
def use_contract_receipt_ocr_client() -> Iterator[None]:
    app.dependency_overrides[get_receipt_ocr_client] = lambda: ReceiptOcrClient()

    yield
    app.dependency_overrides.pop(get_receipt_ocr_client, None)


@pytest.fixture
def override_receipt_ocr_client() -> Iterator[Callable[[ReceiptOcrClientPort], None]]:
    def _override(ocr_client: ReceiptOcrClientPort) -> None:
        app.dependency_overrides[get_receipt_ocr_client] = lambda: ocr_client

    yield _override
    app.dependency_overrides.pop(get_receipt_ocr_client, None)

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import assert_never
from uuid import UUID

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.config.settings import Settings
from app.core.http.auth import set_current_principal
from app.core.security.principal import AuthenticatedPrincipal
from app.main import create_app
from app.modules.auth.api.security import authenticate_current_principal
from app.modules.promotions.application.commands.create_promotion_code_redemption.command import (
    CreatePromotionCodeRedemptionCommand,
)
from app.modules.promotions.application.commands.create_promotion_redemption.command import (
    CreatePromotionRedemptionCommand,
)
from app.modules.promotions.application.commands.create_promotion_redemption.result import (
    CreatePromotionRedemptionResult,
)
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.query import (
    GetCurrentOcrCreditPromotionQuery,
)
from app.modules.promotions.application.queries.get_current_ocr_credit_promotion.result import (
    GetCurrentOcrCreditPromotionResult,
)
from app.modules.promotions.dependencies import (
    get_create_promotion_code_redemption_command_use_case,
    get_create_promotion_redemption_command_use_case,
    get_current_ocr_credit_promotion_query_use_case,
)
from app.modules.promotions.domain.exceptions import (
    PromotionCodeNotFoundError,
    PromotionNotFoundError,
    PromotionRedemptionConflictError,
)
from app.modules.promotions.domain.model import PromotionKind, PromotionRedemptionStatus

TEST_SETTINGS = Settings(app_name="Boat Backend")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000101")
TEST_CREDENTIALS_ID = UUID("00000000-0000-0000-0000-000000000102")
TEST_SESSION_ID = UUID("00000000-0000-0000-0000-000000000103")
PROMOTION_ID = UUID("00000000-0000-0000-0000-000000000201")
REDEMPTION_ID = UUID("00000000-0000-0000-0000-000000000301")
BANNER_IMAGE_URL = "/files/00000000-0000-0000-0000-000000000901/content"
PUBLIC_BANNER_IMAGE_URL = "/api/v1/files/00000000-0000-0000-0000-000000000901/content"


class CurrentPromotionOutcome(StrEnum):
    REDEEMABLE = "redeemable"
    REDEEMABLE_WITHOUT_BANNER = "redeemableWithoutBanner"
    UNAVAILABLE = "unavailable"
    ALREADY_REDEEMED = "alreadyRedeemed"


class RedemptionOutcome(StrEnum):
    GRANTED = "granted"
    ALREADY_REDEEMED = "alreadyRedeemed"
    MISSING_PROMOTION = "missingPromotion"
    MISSING_CODE = "missingCode"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class CurrentPromotionQueryUseCaseStub:
    outcome: CurrentPromotionOutcome

    async def execute(
        self,
        query: GetCurrentOcrCreditPromotionQuery,
    ) -> GetCurrentOcrCreditPromotionResult | None:
        match self.outcome:
            case CurrentPromotionOutcome.REDEEMABLE:
                return _current_result(
                    already_redeemed=False,
                    banner_image_url=BANNER_IMAGE_URL,
                )
            case CurrentPromotionOutcome.REDEEMABLE_WITHOUT_BANNER:
                return _current_result(already_redeemed=False, banner_image_url=None)
            case CurrentPromotionOutcome.UNAVAILABLE:
                return None
            case CurrentPromotionOutcome.ALREADY_REDEEMED:
                return _current_result(
                    already_redeemed=True,
                    banner_image_url=BANNER_IMAGE_URL,
                )
            case unreachable:
                assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class PromotionRedemptionCommandUseCaseStub:
    outcome: RedemptionOutcome
    commands: list[CreatePromotionRedemptionCommand] = field(default_factory=list)

    async def execute(
        self,
        command: CreatePromotionRedemptionCommand,
    ) -> CreatePromotionRedemptionResult:
        self.commands.append(command)
        return _redemption_result_for(self.outcome)


@dataclass(frozen=True, slots=True)
class PromotionCodeRedemptionCommandUseCaseStub:
    outcome: RedemptionOutcome
    commands: list[CreatePromotionCodeRedemptionCommand] = field(default_factory=list)

    async def execute(
        self,
        command: CreatePromotionCodeRedemptionCommand,
    ) -> CreatePromotionRedemptionResult:
        self.commands.append(command)
        return _redemption_result_for(self.outcome)


def promotion_api_app(
    *,
    current_outcome: CurrentPromotionOutcome = CurrentPromotionOutcome.REDEEMABLE,
    redemption_outcome: RedemptionOutcome = RedemptionOutcome.GRANTED,
    code_outcome: RedemptionOutcome = RedemptionOutcome.GRANTED,
    redemption_use_case: PromotionRedemptionCommandUseCaseStub | None = None,
    code_use_case: PromotionCodeRedemptionCommandUseCaseStub | None = None,
) -> FastAPI:
    test_app = create_app(TEST_SETTINGS)
    resolved_redemption_use_case = redemption_use_case or PromotionRedemptionCommandUseCaseStub(
        redemption_outcome
    )
    resolved_code_use_case = code_use_case or PromotionCodeRedemptionCommandUseCaseStub(
        code_outcome
    )
    test_app.dependency_overrides[authenticate_current_principal] = _authenticate_test_principal
    test_app.dependency_overrides[get_current_ocr_credit_promotion_query_use_case] = lambda: (
        CurrentPromotionQueryUseCaseStub(current_outcome)
    )
    test_app.dependency_overrides[get_create_promotion_redemption_command_use_case] = lambda: (
        resolved_redemption_use_case
    )
    test_app.dependency_overrides[get_create_promotion_code_redemption_command_use_case] = lambda: (
        resolved_code_use_case
    )
    return test_app


async def _authenticate_test_principal(request: Request) -> AuthenticatedPrincipal:
    principal = AuthenticatedPrincipal(
        user_id=TEST_USER_ID,
        credentials_id=TEST_CREDENTIALS_ID,
        session_id=TEST_SESSION_ID,
        role="user",
    )
    set_current_principal(request, principal)
    return principal


def api_client(test_app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    )


def _current_result(
    *,
    already_redeemed: bool,
    banner_image_url: str | None,
) -> GetCurrentOcrCreditPromotionResult:
    return GetCurrentOcrCreditPromotionResult(
        promotion_id=PROMOTION_ID,
        name="Internal OCR promotion",
        kind=PromotionKind.MONTHLY_ALLOWANCE,
        benefit_amount=3,
        remaining_redemptions=10,
        max_redemptions_per_user=1,
        remaining_redemptions_for_user=0 if already_redeemed else 1,
        starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        expires_at=datetime(2026, 8, 1, tzinfo=UTC),
        already_redeemed=already_redeemed,
        redemption_status=PromotionRedemptionStatus.GRANTED if already_redeemed else None,
        banner_image_url=banner_image_url,
    )


def _redemption_result_for(outcome: RedemptionOutcome) -> CreatePromotionRedemptionResult:
    match outcome:
        case RedemptionOutcome.GRANTED:
            return _redemption_result(already_redeemed=False, credit_granted=True)
        case RedemptionOutcome.ALREADY_REDEEMED:
            return _redemption_result(already_redeemed=True, credit_granted=False)
        case RedemptionOutcome.MISSING_PROMOTION:
            raise PromotionNotFoundError()
        case RedemptionOutcome.MISSING_CODE:
            raise PromotionCodeNotFoundError()
        case RedemptionOutcome.CONFLICT:
            raise PromotionRedemptionConflictError()
        case unreachable:
            assert_never(unreachable)


def _redemption_result(
    *,
    already_redeemed: bool,
    credit_granted: bool,
) -> CreatePromotionRedemptionResult:
    return CreatePromotionRedemptionResult(
        redemption_id=REDEMPTION_ID,
        promotion_id=PROMOTION_ID,
        promotion_code_id=None,
        status=PromotionRedemptionStatus.GRANTED,
        already_redeemed=already_redeemed,
        credit_granted=credit_granted,
        kind=None,
        benefit_amount=3,
        remaining_redemptions=7,
        max_redemptions_per_user=1,
        remaining_redemptions_for_user=0,
        credit_balance_after=8,
        credit_remaining_after=6,
        banner_image_url=BANNER_IMAGE_URL,
    )

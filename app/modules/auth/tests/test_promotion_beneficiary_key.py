import hashlib
import hmac
from uuid import UUID

import pytest

from app.core.domain.exceptions import ValidationError
from app.modules.auth.domain.model import ExternalIdentity, UserCredential
from app.modules.auth.domain.value_objects import (
    Issuer,
    PromotionBeneficiaryHmacSecret,
    Subject,
)
from app.modules.auth.infrastructure.promotion_beneficiary_key import (
    HmacPromotionBeneficiaryKeyFactory,
)

TEST_HMAC_SECRET = "b" * 48
OTHER_HMAC_SECRET = "c" * 48
TEST_HMAC_SECRET_VALUE = PromotionBeneficiaryHmacSecret(TEST_HMAC_SECRET)


def _factory(
    secret: PromotionBeneficiaryHmacSecret = TEST_HMAC_SECRET_VALUE,
) -> HmacPromotionBeneficiaryKeyFactory:
    return HmacPromotionBeneficiaryKeyFactory(secret=secret)


def _identity(*, identity_id: UUID) -> ExternalIdentity:
    return ExternalIdentity.create(
        issuer="firebase",
        subject="provider-subject-001",
        provider="google",
        email=None,
        name=None,
        identity_id=identity_id,
    )


def test_hmac_beneficiary_key_is_stable_for_same_external_identity() -> None:
    # Given
    identity = _identity(identity_id=UUID("00000000-0000-0000-0000-000000000001"))
    factory = _factory()

    # When
    first_key = factory.create(issuer=identity.issuer, subject=identity.subject)
    second_key = factory.create(issuer=identity.issuer, subject=identity.subject)

    # Then
    assert first_key == second_key


def test_hmac_beneficiary_key_is_independent_from_new_user_identity() -> None:
    # Given
    first_user = UserCredential.create(user_id=UUID("00000000-0000-0000-0000-000000000001"))
    second_user = UserCredential.create(user_id=UUID("00000000-0000-0000-0000-000000000002"))
    identity = _identity(identity_id=UUID("00000000-0000-0000-0000-000000000003"))
    factory = _factory()

    # When
    first_key = factory.create(issuer=identity.issuer, subject=identity.subject)
    second_key = factory.create(issuer=identity.issuer, subject=identity.subject)

    # Then
    assert first_user.user_id != second_user.user_id
    assert first_key == second_key


def test_hmac_beneficiary_key_changes_with_issuer_subject_or_secret() -> None:
    # Given
    identity = _identity(identity_id=UUID("00000000-0000-0000-0000-000000000001"))
    factory = _factory()
    other_factory = _factory(PromotionBeneficiaryHmacSecret(OTHER_HMAC_SECRET))

    # When
    baseline = factory.create(issuer=identity.issuer, subject=identity.subject)
    changed_issuer = factory.create(issuer=Issuer("other-issuer"), subject=identity.subject)
    changed_subject = factory.create(
        issuer=identity.issuer, subject=Subject("provider-subject-002")
    )
    changed_secret = other_factory.create(issuer=identity.issuer, subject=identity.subject)

    # Then
    assert baseline != changed_issuer
    assert baseline != changed_subject
    assert baseline != changed_secret


def test_hmac_beneficiary_key_has_versioned_sha256_shape_and_no_raw_identity() -> None:
    # Given
    identity = _identity(identity_id=UUID("00000000-0000-0000-0000-000000000001"))

    # When
    beneficiary_key = _factory().create(issuer=identity.issuer, subject=identity.subject)
    expected_digest = hmac.new(
        TEST_HMAC_SECRET.encode(),
        b"firebase\0provider-subject-001",
        hashlib.sha256,
    ).hexdigest()

    # Then
    assert beneficiary_key.value == f"v1:{expected_digest}"
    assert len(beneficiary_key.value) == 67
    assert identity.issuer.value not in beneficiary_key.value
    assert identity.subject.value not in beneficiary_key.value


@pytest.mark.parametrize("secret", ["", "   ", "\n"])
def test_promotion_beneficiary_hmac_secret_rejects_empty_or_whitespace_value(secret: str) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        PromotionBeneficiaryHmacSecret(secret)


def test_hmac_factory_constructor_accepts_auth_domain_secret_value_object() -> None:
    # Given
    # When
    factory = HmacPromotionBeneficiaryKeyFactory(
        secret=PromotionBeneficiaryHmacSecret(TEST_HMAC_SECRET)
    )

    # Then
    assert factory.create(
        issuer=_identity(identity_id=UUID("00000000-0000-0000-0000-000000000001")).issuer,
        subject=_identity(identity_id=UUID("00000000-0000-0000-0000-000000000001")).subject,
    ).value.startswith("v1:")

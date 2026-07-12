from app.modules.auth.infrastructure.security.identity_hasher import (
    HmacBenefitSubjectHandleProvider,
)

DEFAULT_NAMESPACE = "boat-backend-firebase"


def _provider(
    *,
    namespace: str = DEFAULT_NAMESPACE,
    version: str = "v1",
    secret: str = "secret-a",  # noqa: S107
    retired_secrets: dict[str, str] | None = None,
) -> HmacBenefitSubjectHandleProvider:
    return HmacBenefitSubjectHandleProvider(
        namespace=namespace,
        current_version=version,
        current_secret=secret,
        retired_secrets=retired_secrets,
    )


def test_handle_is_deterministic_for_same_input() -> None:
    provider = _provider()

    first = provider.handle(subject="firebase-uid-1")
    second = provider.handle(subject="firebase-uid-1")

    assert first == second


def test_handle_has_version_prefix_and_64_char_hex_digest() -> None:
    provider = _provider(version="v1")

    handle = provider.handle(subject="firebase-uid-1")
    version, separator, digest = handle.partition(":")

    assert version == "v1"
    assert separator == ":"
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)


def test_handle_changes_with_secret() -> None:
    handle_a = _provider(secret="secret-a").handle(subject="firebase-uid-1")
    handle_b = _provider(secret="secret-b").handle(subject="firebase-uid-1")

    assert handle_a != handle_b


def test_handle_changes_with_namespace() -> None:
    handle_a = _provider(namespace="namespace-a").handle(subject="firebase-uid-1")
    handle_b = _provider(namespace="namespace-b").handle(subject="firebase-uid-1")

    assert handle_a != handle_b


def test_handle_changes_with_subject() -> None:
    provider = _provider()

    handle_one = provider.handle(subject="firebase-uid-1")
    handle_two = provider.handle(subject="firebase-uid-2")

    assert handle_one != handle_two


def test_handle_is_provider_neutral_because_issuer_is_not_part_of_input() -> None:
    """issuer(google/apple)는 handle() 시그니처 자체에서 제거되어 있다 - 동일
    Firebase uid라면 로그인 수단이 바뀌어도(google -> apple) 같은 handle이 나온다."""
    provider = _provider()

    first_login_handle = provider.handle(subject="shared-firebase-uid")
    second_login_handle = provider.handle(subject="shared-firebase-uid")

    assert first_login_handle == second_login_handle


def test_handle_has_no_separator_ambiguity_between_namespace_and_subject() -> None:
    handle_one = _provider(namespace="a:b").handle(subject="c")
    handle_two = _provider(namespace="a").handle(subject="b:c")

    assert handle_one != handle_two


def test_candidate_handles_returns_only_current_handle_when_no_retired_secrets() -> None:
    provider = _provider()

    candidates = provider.candidate_handles(subject="firebase-uid-1")

    assert list(candidates) == [provider.handle(subject="firebase-uid-1")]


def test_candidate_handles_puts_current_handle_first_and_includes_retired_versions() -> None:
    provider = _provider(
        version="v2",
        secret="secret-v2",
        retired_secrets={"v1": "secret-v1"},
    )
    retired_provider = _provider(version="v1", secret="secret-v1")

    candidates = list(provider.candidate_handles(subject="firebase-uid-1"))

    assert candidates[0] == provider.handle(subject="firebase-uid-1")
    assert candidates[0].startswith("v2:")
    assert retired_provider.handle(subject="firebase-uid-1") in candidates


def test_candidate_handles_supports_multiple_retired_versions_for_rotation_chains() -> None:
    provider = _provider(
        version="v3",
        secret="secret-v3",
        retired_secrets={"v1": "secret-v1", "v2": "secret-v2"},
    )

    candidates = list(provider.candidate_handles(subject="firebase-uid-1"))

    assert len(candidates) == 3
    assert candidates[0] == provider.handle(subject="firebase-uid-1")

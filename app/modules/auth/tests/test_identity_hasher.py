from app.modules.auth.infrastructure.security.identity_hasher import HmacIdentityHasher


def test_hmac_identity_hasher_is_deterministic_for_same_input() -> None:
    hasher = HmacIdentityHasher(secret="secret-a")

    first = hasher.hash(issuer="google", subject="subject-1")
    second = hasher.hash(issuer="google", subject="subject-1")

    assert first == second


def test_hmac_identity_hasher_output_is_64_char_hex() -> None:
    hasher = HmacIdentityHasher(secret="secret-a")

    digest = hasher.hash(issuer="google", subject="subject-1")

    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)


def test_hmac_identity_hasher_output_changes_with_secret() -> None:
    digest_a = HmacIdentityHasher(secret="secret-a").hash(issuer="google", subject="subject-1")
    digest_b = HmacIdentityHasher(secret="secret-b").hash(issuer="google", subject="subject-1")

    assert digest_a != digest_b


def test_hmac_identity_hasher_output_changes_with_issuer() -> None:
    hasher = HmacIdentityHasher(secret="secret-a")

    digest_google = hasher.hash(issuer="google", subject="subject-1")
    digest_apple = hasher.hash(issuer="apple", subject="subject-1")

    assert digest_google != digest_apple


def test_hmac_identity_hasher_output_changes_with_subject() -> None:
    hasher = HmacIdentityHasher(secret="secret-a")

    digest_one = hasher.hash(issuer="google", subject="subject-1")
    digest_two = hasher.hash(issuer="google", subject="subject-2")

    assert digest_one != digest_two

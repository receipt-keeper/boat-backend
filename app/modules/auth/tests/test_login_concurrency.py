import anyio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.auth.application.commands.login.result import LoginResult
from app.modules.auth.domain.model import ExternalIdentity
from app.modules.auth.tests.login_concurrency_support import (
    ConcurrentLoginBarrier,
    ConcurrentLoginContext,
    LoginAttempt,
    LoginOutcome,
    PersistedLoginRows,
    count_persisted_login_rows,
    run_login_attempt,
    seed_registered_identity,
)


async def test_concurrent_login_for_same_existing_external_identity_is_idempotent(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    identity = ExternalIdentity.create(
        issuer="google",
        subject="shared-firebase-uid",
        provider="google",
        email="shared-user@example.com",
        name="동시 로그인 사용자",
        email_verified=True,
    )
    await seed_registered_identity(
        session_factory=postgres_session_factory,
        identity=identity,
    )
    context = ConcurrentLoginContext(
        session_factory=postgres_session_factory,
        identities={
            "provider-token-a": identity,
            "provider-token-b": identity,
        },
        barrier=ConcurrentLoginBarrier(parties=2),
    )
    attempts = [
        LoginAttempt(
            label="request-a",
            provider_token="provider-token-a",
            refresh_token="refresh-token-a",
            refresh_token_hash="refresh-token-hash-a",
        ),
        LoginAttempt(
            label="request-b",
            provider_token="provider-token-b",
            refresh_token="refresh-token-b",
            refresh_token_hash="refresh-token-hash-b",
        ),
    ]
    outcomes: list[LoginOutcome] = []

    async with anyio.create_task_group() as task_group:
        for attempt in attempts:
            task_group.start_soon(run_login_attempt, attempt, context, outcomes)

    ordered_outcomes = sorted(outcomes, key=lambda outcome: outcome.label)
    assert len(ordered_outcomes) == 2
    login_errors = [outcome.error for outcome in ordered_outcomes if outcome.error is not None]
    assert login_errors == []

    results: list[LoginResult] = []
    for outcome in ordered_outcomes:
        assert outcome.result is not None
        results.append(outcome.result)

    token_pairs = {(result.access_token, result.refresh_token) for result in results}
    assert token_pairs == {
        (results[0].access_token, "refresh-token-a"),
        (results[1].access_token, "refresh-token-b"),
    }
    assert all(access_token.startswith("access:") for access_token, _ in token_pairs)

    rows = await count_persisted_login_rows(postgres_session_factory)
    assert rows == PersistedLoginRows(
        users=1,
        credentials=1,
        external_identities=1,
        refresh_tokens=2,
    )


async def test_concurrent_login_for_same_verified_email_links_identities(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    google_identity = ExternalIdentity.create(
        issuer="google",
        subject="google-subject",
        provider="google",
        email="shared-email@example.com",
        name="동시 연결 사용자",
        email_verified=True,
    )
    await seed_registered_identity(
        session_factory=postgres_session_factory,
        identity=google_identity,
    )
    context = ConcurrentLoginContext(
        session_factory=postgres_session_factory,
        identities={
            "google-token": google_identity,
            "apple-token": ExternalIdentity.create(
                issuer="apple",
                subject="apple-subject",
                provider="apple",
                email="shared-email@example.com",
                name="동시 연결 사용자",
                email_verified=True,
            ),
        },
        barrier=ConcurrentLoginBarrier(parties=2),
    )
    attempts = [
        LoginAttempt(
            label="request-a",
            provider_token="google-token",
            refresh_token="refresh-token-a",
            refresh_token_hash="refresh-token-hash-a",
        ),
        LoginAttempt(
            label="request-b",
            provider_token="apple-token",
            refresh_token="refresh-token-b",
            refresh_token_hash="refresh-token-hash-b",
        ),
    ]
    outcomes: list[LoginOutcome] = []

    async with anyio.create_task_group() as task_group:
        for attempt in attempts:
            task_group.start_soon(run_login_attempt, attempt, context, outcomes)

    login_errors = [outcome.error for outcome in outcomes if outcome.error is not None]
    assert login_errors == []
    rows = await count_persisted_login_rows(postgres_session_factory)
    assert rows == PersistedLoginRows(
        users=1,
        credentials=1,
        external_identities=2,
        refresh_tokens=2,
    )

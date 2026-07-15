from __future__ import annotations

import unicodedata

import pytest

from scripts.verify_git_flow import PolicyDecision, cli, verify_git_flow


@pytest.mark.parametrize(
    ("base", "head"),
    [
        ("main", "release/v1.0.2"),
        ("main", "hotfix/auth-fix"),
        ("main", "hotfix/API-fix"),
        ("main", "hotfix/긴급-수정"),
        ("develop", "main"),
        ("develop", "feat/receipt-upload"),
        ("develop", "feat/API-client"),
        ("develop", "feat/a.@"),
        ("develop", "fix/인증-수정"),
        ("develop", "dependabot/uv/fastapi-1.2.3"),
        ("develop", "dependabot/docker/dockerfile-1.2.3"),
        ("release/v1.0.2", "fix/release-blocker"),
        ("release/v1.0.2", "fix/API-bug"),
        ("release/v1.0.2", "58-248-소셜-회원가입-API-추가"),
    ],
)
def test_allowed_git_flow_routes(base: str, head: str) -> None:
    # Given: 보호 브랜치별로 허용된 source branch가 있다.
    # When: Git Flow 경로를 검증한다.
    decision = verify_git_flow(base=base, head=head)

    # Then: 경로가 허용된다.
    assert decision is PolicyDecision.ALLOWED


def test_pr_91_fix_branch_cannot_target_main() -> None:
    # Given: PR #91과 동일한 fix branch -> main 경로가 있다.
    # When: Git Flow 경로를 검증한다.
    decision = verify_git_flow(base="main", head="fix/db-env-components")

    # Then: main 직접 병합이 거부된다.
    assert decision is PolicyDecision.INVALID_ROUTE


def test_pr_42_stacked_riido_pull_request_is_skipped() -> None:
    # Given: PR #42와 동일하게 Riido branch끼리 연결된 stacked PR이 있다.
    # When: Git Flow 경로를 검증한다.
    decision = verify_git_flow(
        base="58-247-소셜-로그인-API-기존-사용자-전용-분리",
        head="58-248-소셜-회원가입-API-추가",
    )

    # Then: 보호 브랜치를 변경하지 않으므로 경로 검사를 생략한다.
    assert decision is PolicyDecision.SKIPPED


@pytest.mark.parametrize(
    "head",
    [
        "58-249-Αλφα",
        "58-249-제목\u202e숨김",
        unicodedata.normalize("NFD", "58-249-한글-제목"),
        "release/v1\u0661.2.3",
    ],
)
def test_invalid_stacked_source_branch_is_rejected(head: str) -> None:
    # Given: 비보호 Riido base를 대상으로 하지만 형식이 유효하지 않은 source branch가 있다.
    # When: stacked PR 경로를 검증한다.
    decision = verify_git_flow(base="58-248-부모-작업", head=head)

    # Then: 경로 관계만 생략하고 source branch 안전성은 거부한다.
    assert decision is PolicyDecision.INVALID_BRANCH


@pytest.mark.parametrize(
    ("base", "head"),
    [
        ("develop", "feat/a..b"),
        ("main", "hotfix/a~b"),
        ("release/v1.0.2", "fix/a.lock"),
        ("58-248-부모-작업", "feat/a@{b"),
        ("develop", "feat/a^b"),
        ("develop", "feat/a?b"),
        ("develop", "feat/a*b"),
        ("develop", "feat/a[b"),
        ("develop", "feat/a\\b"),
        ("develop", "feat/a:b"),
        ("develop", "feat/.hidden"),
        ("develop", "feat/a."),
        ("develop", "dependabot//invalid"),
    ],
)
def test_git_invalid_source_branch_is_rejected(base: str, head: str) -> None:
    # Given: Git ref 문법상 생성할 수 없는 source branch가 있다.
    # When: 보호 또는 stacked PR 경로를 검증한다.
    decision = verify_git_flow(base=base, head=head)

    # Then: 경로 판정보다 먼저 branch 형식이 거부된다.
    assert decision is PolicyDecision.INVALID_BRANCH


def test_riido_branch_cannot_target_main() -> None:
    # Given: 형식이 유효한 Riido branch가 main을 대상으로 한다.
    # When: Git Flow 경로를 검증한다.
    decision = verify_git_flow(base="main", head="58-248-소셜-회원가입-API-추가")

    # Then: main 직접 병합이 거부된다.
    assert decision is PolicyDecision.INVALID_ROUTE


@pytest.mark.parametrize(
    "head",
    [
        "58-248-제목\u202e숨김",
        "58-248-제목\x00숨김",
        "58-248-제목 공백",
        "58-248-제목/하위",
        unicodedata.normalize("NFD", "58-248-한글-제목"),
    ],
)
def test_unsafe_riido_branch_is_rejected(head: str) -> None:
    # Given: 제어문자, 공백, slash 또는 비정규 Unicode가 포함된 Riido branch가 있다.
    # When: develop 대상 경로를 검증한다.
    decision = verify_git_flow(base="develop", head=head)

    # Then: branch 형식이 거부된다.
    assert decision is PolicyDecision.INVALID_BRANCH


@pytest.mark.parametrize(
    "head",
    [
        "58-248-Αλφα",
        "58-248-Кириллица",
        "58-248-漢字",
        "58-248-알림-🔔",
        "58-248-\u3164",
    ],
)
def test_unsupported_riido_title_alphabet_is_rejected(head: str) -> None:
    # Given: 한글, ASCII 영문, 숫자와 허용 구두점 외 문자가 포함된 Riido branch가 있다.
    # When: develop 대상 경로를 검증한다.
    decision = verify_git_flow(base="develop", head=head)

    # Then: branch 형식이 거부된다.
    assert decision is PolicyDecision.INVALID_BRANCH


@pytest.mark.parametrize(
    "head",
    [
        "feature/receipt-upload",
        "release/v1.0",
    ],
)
def test_unsupported_branch_format_is_rejected_for_develop(head: str) -> None:
    # Given: develop에 허용되지 않은 branch 형식이 있다.
    # When: Git Flow 경로를 검증한다.
    decision = verify_git_flow(base="develop", head=head)

    # Then: branch 형식이 거부된다.
    assert decision is PolicyDecision.INVALID_BRANCH


def test_non_semver_release_base_is_skipped() -> None:
    # Given: SemVer 형식이 아니어서 보호 대상이 아닌 release 이름의 base branch가 있다.
    # When: Git Flow 경로를 검증한다.
    decision = verify_git_flow(base="release/next", head="fix/release-blocker")

    # Then: 다른 비보호 branch와 마찬가지로 stacked PR 경로 검사를 생략한다.
    assert decision is PolicyDecision.SKIPPED


def test_release_version_rejects_unicode_digits() -> None:
    # Given: ASCII가 아닌 숫자로 작성한 release branch가 있다.
    # When: main 대상 경로를 검증한다.
    decision = verify_git_flow(base="main", head="release/v1\u0661.2.3")

    # Then: release branch 형식이 거부된다.
    assert decision is PolicyDecision.INVALID_BRANCH


def test_feature_branch_cannot_target_release() -> None:
    # Given: release branch에 허용되지 않은 기능 branch가 있다.
    # When: Git Flow 경로를 검증한다.
    decision = verify_git_flow(base="release/v1.0.2", head="feat/new-feature")

    # Then: release 안정화 범위를 벗어난 경로가 거부된다.
    assert decision is PolicyDecision.INVALID_ROUTE


@pytest.mark.parametrize(
    ("arguments", "expected_exit_code"),
    [
        (["main", "release/v1.0.2"], 0),
        (["main", "fix/direct-main"], 1),
        ([], 2),
        (["main", "release/v1.0.2", "extra"], 2),
    ],
)
def test_cli_exit_code(arguments: list[str], expected_exit_code: int) -> None:
    # Given: CI가 전달할 정상, 정책 위반 또는 잘못된 개수의 인자가 있다.
    # When: CLI 경계에서 인자를 처리한다.
    exit_code = cli(arguments)

    # Then: 성공, 정책 위반, 사용법 오류가 서로 다른 종료 코드로 반환된다.
    assert exit_code == expected_exit_code

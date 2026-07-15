# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# ─── How to run ───
# uv run python scripts/verify_git_flow.py <base-branch> <head-branch>

from __future__ import annotations

import re
import sys
import unicodedata
from collections.abc import Sequence
from enum import StrEnum
from typing import Final, assert_never

RELEASE_PATTERN: Final = re.compile(
    r"release/v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
)
CONVENTIONAL_PATTERN: Final = re.compile(r"(?:feat|fix|refactor|test|docs|chore|ci)/[^/]+")
RELEASE_TOPIC_PATTERN: Final = re.compile(r"(?:fix|test|docs|chore|ci)/[^/]+")
HOTFIX_PATTERN: Final = re.compile(r"hotfix/[^/]+")
DEPENDABOT_PATTERN: Final = re.compile(r"dependabot/.+")
RIIDO_PATTERN: Final = re.compile(r"[A-Za-z0-9]+-[0-9]+-(?P<title>.+)")
RIIDO_PUNCTUATION: Final = frozenset("-_.")
GIT_FORBIDDEN_CHARACTERS: Final = frozenset({" ", "~", "^", ":", "?", "*", "[", "\\"})


class PolicyDecision(StrEnum):
    ALLOWED = "allowed"
    SKIPPED = "skipped"
    INVALID_BRANCH = "invalid_branch"
    INVALID_ROUTE = "invalid_route"


class BaseKind(StrEnum):
    MAIN = "main"
    DEVELOP = "develop"
    RELEASE = "release"
    OTHER = "other"


def _full_match(pattern: re.Pattern[str], branch: str) -> bool:
    return pattern.fullmatch(branch) is not None


def _is_globally_safe(branch: str) -> bool:
    if not branch or unicodedata.normalize("NFC", branch) != branch:
        return False
    if not all(
        not character.isspace() and unicodedata.category(character)[0] not in {"C", "Z"}
        for character in branch
    ):
        return False
    if branch == "@" or ".." in branch or "@{" in branch:
        return False
    return all(
        component
        and not component.startswith(".")
        and not component.endswith(".")
        and not component.endswith(".lock")
        and all(character not in GIT_FORBIDDEN_CHARACTERS for character in component)
        for component in branch.split("/")
    )


def _is_riido_title_character(character: str) -> bool:
    unicode_name = unicodedata.name(character, "")
    return (
        (character.isascii() and character.isalnum())
        or character in RIIDO_PUNCTUATION
        or (unicode_name.startswith("HANGUL ") and not unicode_name.endswith("FILLER"))
    )


def _is_riido_branch(branch: str) -> bool:
    matched = RIIDO_PATTERN.fullmatch(branch)
    if matched is None or "/" in branch:
        return False
    title = matched.group("title")
    return all(_is_riido_title_character(character) for character in title)


def _is_release_branch(branch: str) -> bool:
    return _full_match(RELEASE_PATTERN, branch)


def _is_known_branch(branch: str) -> bool:
    return (
        branch == "main"
        or _full_match(CONVENTIONAL_PATTERN, branch)
        or _full_match(HOTFIX_PATTERN, branch)
        or _full_match(DEPENDABOT_PATTERN, branch)
        or _is_release_branch(branch)
        or _is_riido_branch(branch)
    )


def _classify_base(base: str) -> BaseKind:
    match base:
        case "main":
            return BaseKind.MAIN
        case "develop":
            return BaseKind.DEVELOP
        case release if _is_release_branch(release):
            return BaseKind.RELEASE
        case _:
            return BaseKind.OTHER


def verify_git_flow(base: str, head: str) -> PolicyDecision:
    base_kind = _classify_base(base)
    if not _is_globally_safe(head) or not _is_known_branch(head):
        return PolicyDecision.INVALID_BRANCH

    match base_kind:
        case BaseKind.OTHER:
            return PolicyDecision.SKIPPED
        case BaseKind.MAIN | BaseKind.DEVELOP | BaseKind.RELEASE:
            pass
        case unreachable:
            assert_never(unreachable)

    match base_kind:
        case BaseKind.MAIN:
            allowed = _is_release_branch(head) or _full_match(HOTFIX_PATTERN, head)
        case BaseKind.DEVELOP:
            allowed = (
                head == "main"
                or _full_match(CONVENTIONAL_PATTERN, head)
                or _full_match(DEPENDABOT_PATTERN, head)
                or _is_riido_branch(head)
            )
        case BaseKind.RELEASE:
            allowed = _full_match(RELEASE_TOPIC_PATTERN, head) or _is_riido_branch(head)
        case BaseKind.OTHER:
            raise AssertionError(base_kind)
        case unreachable:
            assert_never(unreachable)
    return PolicyDecision.ALLOWED if allowed else PolicyDecision.INVALID_ROUTE


def main(base: str, head: str) -> int:
    decision = verify_git_flow(base=base, head=head)
    match decision:
        case PolicyDecision.ALLOWED:
            print(f"브랜치 정책 통과: {head} -> {base}")
            return 0
        case PolicyDecision.SKIPPED:
            print(f"비보호 base 브랜치이므로 경로 검사를 생략합니다: {head} -> {base}")
            return 0
        case PolicyDecision.INVALID_BRANCH:
            print(f"source 브랜치 형식이 올바르지 않습니다: {head}", file=sys.stderr)
            return 1
        case PolicyDecision.INVALID_ROUTE:
            print(f"허용되지 않은 Git Flow 경로입니다: {head} -> {base}", file=sys.stderr)
            return 1
        case unreachable:
            assert_never(unreachable)


def cli(arguments: Sequence[str]) -> int:
    if len(arguments) != 2:
        usage = "사용법: python scripts/verify_git_flow.py <base-branch> <head-branch>"
        print(usage, file=sys.stderr)
        return 2
    return main(base=arguments[0], head=arguments[1])


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))

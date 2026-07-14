from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def expected_release_tag() -> str:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as pyproject_file:
        project = tomllib.load(pyproject_file)["project"]
    version = project["version"]
    return f"v{version}"


def main(tag: str) -> int:
    expected = expected_release_tag()
    if tag != expected:
        print(f"release tag 불일치: 입력={tag}, 기대={expected}", file=sys.stderr)
        return 1
    print(f"release tag 검증 통과: {tag}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python scripts/verify_release_version.py <tag>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))

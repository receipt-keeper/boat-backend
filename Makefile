.PHONY: install lint format typecheck test check

install:
	uv sync --all-groups
	uv run pre-commit install

lint:
	uv run ruff check

format:
	uv run ruff format

typecheck:
	uv run pyright

test:
	uv run pytest

check:
	uv run ruff check
	uv run ruff format --check
	uv run pyright
	uv run pytest

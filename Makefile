.PHONY: format format-check lint typecheck test build check

format:
	uv run --locked ruff format .

format-check:
	uv run --locked ruff format --check .

lint:
	uv run --locked ruff check .

typecheck:
	uv run --locked mypy .

test:
	uv run --locked python -m pytest

build:
	uv run --locked python -m compileall app
	uv run --locked python -c "import app.main"

check: format-check lint typecheck test build

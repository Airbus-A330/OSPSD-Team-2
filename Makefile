.PHONY: format format-check lint typecheck test build check

format:
	ruff format .

format-check:
	ruff format --check .

lint:
	ruff check .

typecheck:
	mypy .

test:
	python -m pytest

build:
	python -m compileall app
	python -c "import app.main"

check: format-check lint typecheck test build

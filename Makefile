.PHONY: format format-check lint typecheck test build check reliability-check

PROMTOOL ?= promtool
AMTOOL ?= amtool

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

reliability-check:
	$(PROMTOOL) check rules reliability/calendar.rules.yml
	cd reliability && $(PROMTOOL) test rules rules.test.yml
	$(AMTOOL) check-config reliability/alertmanager.yml.example

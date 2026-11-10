.PHONY: format format-check lint typecheck test build check reliability-check reliability-report

PROMTOOL ?= promtool
AMTOOL ?= amtool
PROMETHEUS_URL ?= http://127.0.0.1:9090

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

reliability-report:
	@curl --fail --silent --show-error --max-time 30 --get "$(PROMETHEUS_URL)/api/v1/query" \
		--data-urlencode 'query={__name__=~"team2_calendar:get_.*:(increase7d|ratio7d|budget7d)"}' \
		--data-urlencode "time=$$(date -u +%Y-%m-%dT%H:%M:%SZ)"

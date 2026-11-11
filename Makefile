.PHONY: format format-check lint typecheck test build check conformance reliability-check reliability-report

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

conformance:
	uv run --locked python -m pytest tests/integration/test_shared_conformance.py

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

# Issue #68: local artifact and IaC checks; neither target deploys anything.
CONTAINER_IMAGE ?= ospsd-team2-issue68:local
.PHONY: container-build infra-check
container-build:
	docker build --platform linux/amd64 --provenance=false -t $(CONTAINER_IMAGE) .

infra-check:
	@blueprint=$$(mktemp /tmp/ospsd-render-XXXXXX.yaml); \
	trap 'rm -f "$$blueprint"' EXIT; \
	python3 scripts/render_blueprint.py --image ghcr.io/airbus-a330/ospsd-team-2@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa > "$$blueprint" && \
	uv tool run --from check-jsonschema==0.37.0 check-jsonschema --schemafile https://render.com/schema/render.yaml.json "$$blueprint"

.PHONY: container-check
container-check:
	docker run --rm --platform linux/amd64 --network none -i $(CONTAINER_IMAGE) python - < scripts/check_container.py

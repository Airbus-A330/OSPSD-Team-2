# Local delivery implementation verification — 2026-11-10

This is controlled local evidence only, not a deployed release or rollback.
Base: `assgn2-ms3-submission`, commit
`692597cc799b2f5e640c142eee6986106c92a848`. Changes were uncommitted during checks.
Platform: native Windows, CPython 3.12.14, uv 0.12.17. GNU Make was unavailable,
so the documented uv equivalents of `make check` were executed. uv was installed
as temporary tooling and invoked by its absolute path, with no dependency changes.

| Command | Actual result |
| --- | --- |
| `uv sync --locked` | PASS; supported Python environment and locked dependencies installed |
| `uv run --locked ruff format scripts/deploy_render.py scripts/smoke_calendar.py tests/test_delivery.py` | PASS; new Python files formatted (also rerun on changed subsets) |
| `uv run --locked ruff format --check .` | PASS; 51 files formatted |
| `uv run --locked ruff check .` | PASS |
| `uv run --locked mypy scripts` | PASS; initial focused check |
| `uv run --locked mypy .` | PASS; 51 source files |
| `uv run --locked python -m pytest tests/test_delivery.py -q` | PASS; final 15 focused tests |
| `uv run --locked python -m pytest` | PASS before final safeguards; 874 passed, 1 skipped |
| `uv run --locked python -m pytest -q` | PASS final code; 876 passed, 1 skipped |
| `uv run --locked python -m pytest tests/integration/test_shared_conformance.py -q` | PASS; 54 cases through controlled Python/HTTP boundaries |
| `uv run --locked python -m compileall app` | PASS |
| `uv run --locked python -c "import app.main"` | PASS |
| `actionlint -shellcheck=` (v1.7.7) | PASS; workflow syntax/expressions validated, ShellCheck unavailable/disabled |
| `uv run --locked python scripts/render_blueprint.py --image <synthetic-digest-reference>` | PASS; existing renderer used with `ghcr.io/airbus-a330/ospsd-team-2@sha256:` plus 64 `a` characters |
| `uv tool run --from check-jsonschema==0.37.0 check-jsonschema --schemafile https://render.com/schema/render.yaml.json <temporary-blueprint>` | PASS; official schema, equivalent to `make infra-check`; no apply |
| `git diff --check` | PASS |
| `docker info --format '{{.ServerVersion}}'` | BLOCKED; Docker daemon not running; container build/check not executed |

The skipped test is the explicitly opt-in real Google workflow. One existing
Starlette/AnyIO deprecation warning remains. No live smoke, registry publication,
GitHub-hosted CI run, platform-aware Render validation, deployment or faulty
revision/rollback exercise was executed. Those require configured environments,
credentials, an infrastructure owner and explicit authorization from the user.
Initial sandbox attempts to run Python/read public API docs were denied; approved
escalated tooling then enabled the local checks. No auto-review rejection occurred.

Self-review covered tracked/untracked changed files, digest selection, credential
boundaries, concurrency, failure evidence, cleanup and accidental secret exposure.
Only synthetic test credentials are present in tests; runtime credentials come
from protected environment inputs. Container context remains #68's allowlist.

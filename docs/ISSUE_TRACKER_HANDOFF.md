# Team 4 Issue Tracker integration handoff

The supplied `OSPSD-Team-4-main` archive identifies the shared dependency as
`issue-tracker-contract==1.1.0`, from the `contract` subdirectory of
`https://github.com/Tyler-Arciniaga/OSPSD-Team-4.git` at tag
`issue-tracker-contract-v1.1.0`. Its `IssueProvider.create_issue(title)`
returns an `Issue` with `id` and `title`; failures use the contract's
`ServiceError`. Trello requires `TRELLO_API_KEY`, `TRELLO_TOKEN`, and
`TRELLO_LIST_ID`; Linear requires `LINEAR_API_KEY` and `LINEAR_TEAM_ID`.

## Original integration blocker and reproduction

The supplied implementation is a service source tree, rather than an
independently named provider package. Its root `pyproject.toml` declares no
build system, and its providers are `app.providers.trello_provider` and
`app.providers.linear_provider`. They import `app.providers.common` and
`app.telemetry` by that same absolute package name. Team 2 already owns the
top-level `app` package. Consequently, adding the source tree to Python's
import path cannot make both applications' `app` packages independently
importable in the normal way.

Reproduce from the two source trees: compare the `app/` directories and inspect
the imports at the top of Team 4's `app/providers/trello_provider.py`. From the
Team 2 repository root, `import app` resolves Team 2's package, so importing
`app.providers.trello_provider` cannot resolve Team 4's provider. This is a
packaging boundary mismatch, not evidence of an incompatibility in the shared
`IssueProvider` signature.

The original archive needed a versioned, installable implementation with a distinct
top-level Python package and its internal imports updated accordingly. Team 4 published
`team-4-issue-tracker-trello-v1.0.0`, which provides the distinct import
`team_4_issue_tracker_trello` and resolves the collision. Team 2 pins that tag
and the contract tag in `pyproject.toml` and `uv.lock`.

## Configuration and behavior

Set `ISSUE_TRACKER_IMPLEMENTATION=team4-trello` and supply all three Trello
variables above. Missing or unsupported selection and missing or whitespace-only credentials fail
at Issue Tracker setup before any workflow writes. The adapter closes the Team 4
provider after each workflow. It translates shared invalid-input, not-found,
access-denied, and unconfigured errors to corresponding Team 2 errors; other
shared failures become provider errors. Provider details are not returned to
the caller. Workflow writes are never automatically retried; provider failures
are conservatively reported as uncertain even when Team 4 can prove rejection.
The package reads its environment on each provider call; keep credentials in
external secret configuration, never in the repository.

## Verification status

The tagged contract and Trello package were resolved and installed locally.
`tests/integration/test_issue_tracker_package.py` exercises the actual package
through the HTTP workflow with Trello HTTP controlled: successful creation,
permission rejection, and an uncertain provider failure. The tests also verify
progress and that the workflow does not retry a write. They do not prove live
provider behavior.

For direct live verification, configure the selection and Trello variables
above for a dedicated disposable test list, then run:

```bash
RUN_LIVE_ISSUE_TRACKER=1 uv run --locked python -m pytest -s tests/live/test_issue_tracker_workflow.py
```

The opt-in test creates an issue through Team 2's configured factory, reads the
returned card directly from Trello to check its ID, title and list, and deletes
a confirmed creation. If creation fails without an ID, inspect the list for the
printed unique title before retrying; a write could have succeeded despite a
lost response. This test verifies the Issue Tracker integration, not the full
three-provider workflow or deployment.

Team 4's packaging collision is resolved, and its tagged package installs and
constructs alongside Team 2 without a namespace collision. Automated tests use
the installed package through the configured factory and controlled Trello HTTP.
The deployment operator also completed a direct Trello API create/read/delete
check and confirmed cleanup, as recorded in
[HW3_DEPLOYMENT.md](HW3_DEPLOYMENT.md#direct-trello-api-check-2026-11-18).
Provider-backed testing through the configured Team 4 integration also
completed successfully; an exact timestamp was not retained. The direct check
separately proves the disposable target and cleanup behavior. Neither check is a
retained hosted three-provider workflow run.

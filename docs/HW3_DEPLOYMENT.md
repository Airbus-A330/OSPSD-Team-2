# HW3 deployment and verification

Status: the Milestone 1 composition, package integrations, deployment
configuration, controlled verification, and provider-specific checks described
below are complete. The evidence ledger distinguishes those results from the
completed hosted three-provider verification from the remaining real
package-swap limit. Faisal from Team 6 completed the external design review;
the response is recorded in DESIGN.md.

## Reuse the HW2 delivery path

The existing image-backed Render service is the deployment destination:
`https://ospsd-team-2-5ogi.onrender.com`, with `/readyz` as its health check.
The existing Delivery workflow now selects `hw3-ms1-submission`. Build, Format,
Tests, Infrastructure, the tested immutable image, and the Render deployment
script are reused. There is no second production service or new CD system.

For HW3 delivery, the repository administrator must allow `hw3-ms1-submission`
in the production environment's deployment-branch rules and protect the branch
as described in [DELIVERY.md](DELIVERY.md). Do not push or dispatch the old
`assgn2-ms3-submission` workflow during HW3 delivery: its historical workflow
still exists on that branch and could deploy an old image to the same service.
The shared concurrency group prevents simultaneous runs, not stale releases.

GitHub configuration stays the same: secrets `RENDER_API_KEY` and
`CALENDAR_API_TOKEN`; variables `RENDER_SERVICE_ID` and `CALENDAR_BASE_URL`.
Do not copy Google/Dropbox/Trello provider credentials into GitHub for this flow.
Render configuration changes are a separate operator step: deploying an image
does not apply the generated Blueprint or update environment variables.

## Render configuration checklist

Preserve the existing Google Calendar, API token, port, and telemetry settings.
Add these values in the service's Environment page. The matching Blueprint
entries document bootstrap requirements; do not create another service by
applying the template blindly.

| Variable | Value / source |
| --- | --- |
| `WORKFLOW_IMPLEMENTATION` | `configured` |
| `CALENDAR_IMPLEMENTATION` | `team2` |
| `STORAGE_IMPLEMENTATION` | `team3` |
| `ISSUE_TRACKER_IMPLEMENTATION` | `team4-trello` |
| `DROPBOX_APP_KEY` | Dedicated test app, coordinate with Nicolas (#82) |
| `DROPBOX_APP_SECRET` | External secret from the test app owner |
| `DROPBOX_REFRESH_TOKEN` | Authorized test-account refresh token |
| `TRELLO_API_KEY` | Dedicated test app provisioned by the deployment operator; see the Trello check below |
| `TRELLO_TOKEN` | Authorized token for that test account |
| `TRELLO_LIST_ID` | Dedicated disposable test list |

`WORKFLOW_FAIL_STEP` must be absent in configured mode. Use refresh-token
Dropbox configuration rather than a short-lived token for hosted execution.
Use the same test account when directly inspecting records. Credential owners
must share through an agreed private channel, never PRs, screenshots, or logs.
See [STORAGE.md](STORAGE.md) and [ISSUE_TRACKER_HANDOFF.md](ISSUE_TRACKER_HANDOFF.md)
for provider-specific setup and tagged package references.

## Three distinct verification layers

1. `make check` and `make container-check`: credential-free tests. The container
   check now exercises a controlled storage failure through the protected HW3
   HTTP route, proving installed imports and progress reporting in the image.
2. Delivery's existing Calendar smoke: real Google CRUD and cleanup after the
   identified immutable Render deployment. A green Delivery alone does **not**
   prove the composed operation, Dropbox, Trello, or a configuration-only swap.
3. `make verify-kickoff`: explicitly opted-in hosted three-step request, followed
   by direct inspection and cleanup below. The script is separate from automatic
   delivery because it retains records for provider inspection and has no shared
   workflow deletion endpoint. It never claims that manual inspection is done.

## Run the deployed operation

From a locked checkout of the submitted revision, set `CALENDAR_BASE_URL` to the
service origin and supply the existing `CALENDAR_API_TOKEN` in the local process
environment via your private credential mechanism. Then:

```sh
uv sync --locked
make verify-kickoff
```

This makes one request to `POST /workflows/project-kickoff`, creating an event,
a Markdown file, and a Trello card with a shared unique `ospsd-kickoff-...`
marker. The script checks HTTP 201 and the combined fields, with no automatic
write retries. It saves only sanitized metadata to an ignored
`.runtime/kickoff-.../verification.json`. It does not print response bodies,
provider IDs, credentials, or exception text. Its generated marker is test-only
and supports locating records after a lost response.

If readiness fails, no workflow write has been attempted. If the request or
response validation fails, inspect all three providers by that marker before
retrying. Do not interpret a timeout as a failed write. A repeat of the same
workflow is not idempotent.

For a human/API-client demonstration, the request shape is:

```json
{
  "event": {
    "title": "Project kickoff UNIQUE-MARKER",
    "start": "2030-01-07T15:00:00Z",
    "end": "2030-01-07T15:30:00Z"
  },
  "document_path": "/kickoff-UNIQUE-MARKER.md",
  "document_content": "# Project kickoff UNIQUE-MARKER\n",
  "issue_title": "Project kickoff UNIQUE-MARKER"
}
```

Send `Authorization: Bearer <existing API token>` and
`Content-Type: application/json`. Use a fresh unique marker and test-owned
resources only. Browser navigation to `/` without that header remains denied.

## Direct provider verification and cleanup

For the exact marker in the report, record time, source SHA, image digest and
Render deployment ID (from Delivery evidence), then independently inspect:

- Google Calendar: matching title and start/end instants in the designated calendar.
- Dropbox: exact generated path and Markdown content, not just file existence.
- Trello: matching card title in the designated test list.

Use each provider's UI or direct API, not only the combined response or cached
Calendar GET. Retain redacted screenshots or safe check results. Delete only
these test-owned records after collecting proof and confirm absence in each
provider. Record partial/uncertain writes and cleanup failures honestly; do not
claim cleanup merely because the local script finished.

## Controlled failure exercise

Use a local test instance or an explicitly authorized isolated test deployment;
do not switch the shared production service while teammates are using it.
Set `WORKFLOW_IMPLEMENTATION=controlled` and `WORKFLOW_FAIL_STEP=storage`, then:

```sh
uv run --locked python -m scripts.verify_kickoff --allow-create --expected-failure storage
```

The script expects 403, `failed_step=storage`, `failure_stage=operation`,
`retryable=false`, Storage failed, and both Issue Tracker and Calendar not attempted.
Confirm the instance really has controlled configuration before interpreting it
as synthetic: the HTTP error alone cannot prove no external writes occurred.
Restore configured mode and remove `WORKFLOW_FAIL_STEP` afterward. This exercise
is failure-path evidence, **not** a genuine implementation-swap demonstration.

## Submission evidence ledger

Keep generated reports local until reviewed for redaction. Exact hosted run
identifiers are intentionally absent where no retained evidence exists.

| Requirement | Evidence / status |
| --- | --- |
| HW3 workflow and deployment configuration | PASS — automated verification; Blueprint, route, configured package construction and verifier tests pass |
| Exact HW3 Delivery run, source SHA, image digest, Render deploy ID | PASS — exact Delivery, source SHA, image digest and both Render deployment IDs recorded below |
| Hosted three-step happy path | PASS — HTTP 201 at 2026-11-18T23:45:43.945189+00:00; all three steps succeeded |
| Direct provider verification | PASS — composed-run Calendar title/time, exact Dropbox filename/content and Trello card independently verified |
| Test-record cleanup | PASS — all three composed-run records deleted; absence confirmed through direct APIs and UI |
| Controlled step-aware failure | PASS — automated verification and local offline-container storage-failure exercise; see 2026-11-18 check below |
| Genuine configuration-only implementation swap | EVIDENCE LIMIT — no compatible second storage package was available; see DESIGN.md |
| Architecture and request trace | [DESIGN.md](DESIGN.md#hw3-deployment-and-request-trace-85) |
| External-team design review and substantive responses | PASS — Faisal from Team 6 identified three substantive concerns; the implemented response is retained in DESIGN.md |

A second compatible real implementation must be packaged, pinned and selectable
before the swap exercise can run. Preserve the same image digest across the
before/after configuration-only demonstration. Do not report the controlled
fake or a changed-code deployment as satisfying that requirement.

## Hosted evidence and deployment provenance (2026-11-18)

The [PR evidence comment](https://github.com/Airbus-A330/OSPSD-Team-2/pull/89#issuecomment-6995518658)
retains sanitized workflow, cleanup and Delivery reports.

- Submitted/build SHA: `e5f0135006c1cca66506a61d596441f9e4a86f0e` on
  `hw3-ms1-submission`; this does not assert PR #89 has merged into master.
- [Delivery run 44410995133, attempt 1](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/44410995133):
  Build, Format, Tests, Infrastructure, artifact and deploy jobs succeeded.
- Immutable image:
  `ghcr.io/airbus-a330/ospsd-team-2@sha256:d1ab9453014d771b6af5f439f9b7d1fcf109c74b07fd7b29cf2abd06401094f6`.
- [Delivery artifact](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/44410995133/artifacts/14477935218):
  `delivery.json` / `delivery.yaml`, also retained locally. CI deployment
  `dep-dbv2b16tlv9c73fjaeq0` reached live; Calendar smoke passed and cleanup was confirmed.
- Subsequent [environment-update deployment](https://dashboard.render.com/web/srv-dbprkbh5efls738r7rf0/deploys/dep-dbv3gtrl550s738jrnqg):
  `dep-dbv3gtrl550s738jrnqg`, same immutable image, triggered by the operator's
  environment update on November 18 at 6:44:55 PM EST. Render reported live at
  6:45:28 PM EST, before the successful composed test at 6:45:43 PM EST.
  This is distinct from the earlier CI deployment ID.
- Test marker: `ospsd-kickoff-304fd548d1674ac0a846fbad83782a7c`.
- Google event: January 7, 2030, 15:00–15:30 UTC (10:00–10:30 AM New York).
  Dropbox exact Markdown content and Trello matching card were independently verified.
- Cleanup preflight found exactly one matching record per provider; all three
  outcomes were `deleted_verified`, reported at 2026-11-19T00:02:18.612550+00:00.
  Subsequent UI checks confirmed absence.

The original workflow report's pending/retained fields describe its initial state;
later inspection and cleanup are documented separately without rewriting that report.
Delivery's Calendar smoke and the subsequent three-provider run are separate checks.
The external-team design review is complete. Genuine implementation-swap
evidence remains unavailable because no second compatible package was released.

## Historical local preparation check (2026-11-17)

On the uncommitted #85 working tree based on `7892b35`:

- `make check`: 1042 passed, 3 opt-in live tests skipped; formatting, lint,
  types, compilation and import passed. One existing dependency deprecation warning.
- `make infra-check`: generated Blueprint passed schema validation.
- `make container-build container-check infra-check`: stopped while Docker was
  still resolving pinned Python/uv base-image metadata. No new image or container
  check result is claimed. The independent infrastructure check above passed.
- No cloud deployment, credential changes, provider writes or external review
  were performed as part of this preparation. The later Docker and provider
  checks below supersede the preparation-stage gaps they directly cover.

## Local Docker and failure checks (2026-11-18)

Tested source revision `69c0d2f` on the issue #85 branch:

- `make container-build container-check CONTAINER_IMAGE=ospsd-team2-issue85:local`
  passed with the pinned Linux/amd64 base images and locked dependencies.
  Local image ID: `sha256:5569b85df31673dbccb1e48241842979d6f8ae965b18ecba3269f974cbe998ba`.
- The disposable container ran with `--network none` and synthetic credentials.
  Checks covered non-root startup, rejection of missing configuration, ephemeral
  token-cache recovery, readiness, authentication, and the real HTTP workflow
  route with a controlled storage failure: Calendar succeeded, Storage failed,
  Issue Tracker was not attempted, and `retryable` was false.
- `uv run --locked python -m pytest -q tests/test_project_kickoff_workflow.py tests/test_workflow_composition.py tests/test_verify_kickoff.py`:
  83 passed; one existing Starlette/AnyIO deprecation warning. This covers each
  step's failure, setup failures before writes, partial progress, no automatic
  retries, client cleanup, uncertain writes, and sanitized verification reports.
- These are local synthetic checks, not hosted three-provider acceptance or a
  real implementation swap. No Render configuration or deployment was changed.
  This retained run used the earlier Calendar-first sequence; Faisal's external
  review led to the safer Storage-first sequence now covered by current tests.

## Direct Trello API check (2026-11-18)

At 20:20:45 UTC, the deployment operator verified the test account's API key and
token directly against the Trello REST API from a local process. The target was
the private `OSPSD Team 2 Test` board's `API Test` list. The disposable card used
the unique marker `OSPSD disposable API verification 8ec59573c2aa`.

| Check | Observed result |
| --- | --- |
| Read target list and confirm its name | HTTP 200; `API Test` matched |
| Create disposable card | HTTP 200; card ID returned |
| Read the created card | HTTP 200; title, description and list ID matched |
| Delete that test card | HTTP 200 |
| Read the deleted card again | HTTP 404; cleanup confirmed |

All five checks passed. Credentials were supplied only to the local test process
and are excluded from this evidence. No Render settings or deployment changed.
This verifies Trello credential access and direct API create/read/delete behavior;
it does not exercise the shared issue-tracker adapter or the composed HTTP route.
The installed Team 4 package and workflow integration are covered by automated
tests, and provider-backed testing through that configured integration also
completed successfully without a retained exact timestamp. The later hosted
three-provider verification and cleanup are recorded above.

## Milestone 1 verification summary

| Assignment requirement | Status | Evidence |
| --- | --- | --- |
| Fixed Storage → Issue Tracker → Calendar API workflow and combined result | PASS — automated verification | Workflow, HTTP, and composition tests exercise all three steps and HTTP 201 |
| Provider-independent orchestration | PASS — automated verification | Workflow tests use narrow capabilities and contain no provider SDK construction |
| Team 2 Calendar through the shared contract | PASS — automated verification | Configured Calendar composition and shared-contract integration tests |
| Team 3 Cloud Storage package through the tagged shared contract | PASS — automated verification | Locked package construction and integration tests |
| Team 3 provider-backed storage behavior | PASS — manually verified | 2026-11-16 Dropbox create/read/exact-content/duplicate/delete check |
| Team 4 Issue Tracker package through the tagged shared contract | PASS — automated verification | Corrected package installs without namespace collision; construction and controlled-HTTP integration tests pass |
| Team 4 provider-backed integration | PASS — manually verified | Configured Trello integration succeeded; direct create/read/delete/absence check is recorded above |
| Configuration-driven implementation selection and fail-closed setup | PASS — automated verification | Composition tests cover supported/unsupported selection and missing configuration before writes |
| Failed-step and partial-success reporting | PASS — automated verification | Storage, Issue Tracker, and Calendar failure cases retain earlier results and mark later steps unattempted |
| Retry and duplicate-work safety | PASS — automated verification | No automatic write retry/rollback; repeated-run and uncertain-write tests document reconciliation requirements |
| Locked build, deployment configuration, and controlled container path | PASS — automated verification | Locked checks, Blueprint validation, container build/check and offline workflow failure exercise |
| Hosted composed happy path with direct confirmation in all three providers | PASS — hosted verification | Sanitized HTTP 201 report, direct provider checks and confirmed cleanup linked above |
| Genuine configuration-only swap between two real implementations | EVIDENCE LIMIT | Team 1 and Team 6 releases were not compatible installable alternatives |
| External-team integration-design review | PASS | Faisal from Team 6 identified ordering, validation, and conflict-semantics issues; the response is recorded in DESIGN.md |

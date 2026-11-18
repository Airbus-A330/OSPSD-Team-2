# HW3 deployment and verification (#85)

Status: deployment preparation. No new hosted three-provider verification,
implementation swap, or external design approval is claimed by this document.

## Reuse the HW2 delivery path

The existing image-backed Render service is the deployment destination:
`https://ospsd-team-2-5ogi.onrender.com`, with `/readyz` as its health check.
The existing Delivery workflow now selects `hw3-ms1-submission`. Build, Format,
Tests, Infrastructure, the tested immutable image, and the Render deployment
script are reused. There is no second production service or new CD system.

Before merging, the repository administrator must allow `hw3-ms1-submission`
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
| `TRELLO_API_KEY` | Dedicated test app, coordinate with Dorien (#83) |
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
`retryable=false`, Calendar succeeded, Storage failed, Issue Tracker not attempted.
Confirm the instance really has controlled configuration before interpreting it
as synthetic: the HTTP error alone cannot prove no external writes occurred.
Restore configured mode and remove `WORKFLOW_FAIL_STEP` afterward. This exercise
is failure-path evidence, **not** a genuine implementation-swap demonstration.

## Submission evidence ledger

Keep generated reports local until reviewed for redaction. Add links and exact
revisions here after performing each action; do not fill pending items with
sample results.

| Requirement | Evidence / status |
| --- | --- |
| HW3 Delivery run, source SHA, image digest, Render deploy ID | Pending reviewed merge and run |
| Hosted three-step happy path | Pending external credentials and deployment |
| Direct Calendar / Dropbox / Trello confirmation | Pending |
| Test-record cleanup | Pending |
| Controlled step-aware failure | Pending recorded exercise |
| Genuine configuration-only implementation swap | Blocked: no supported second implementation; see DESIGN.md |
| Architecture and request trace | [DESIGN.md](DESIGN.md#hw3-deployment-and-request-trace-85) |
| External-team design review and substantive responses | Pending review request and response links |

A second compatible real implementation must be packaged, pinned and selectable
before the swap exercise can run. Preserve the same image digest across the
before/after configuration-only demonstration. Do not report the controlled
fake or a changed-code deployment as satisfying that requirement.

## Local preparation check (2026-11-17)

On the uncommitted #85 working tree based on `7892b35`:

- `make check`: 1042 passed, 3 opt-in live tests skipped; formatting, lint,
  types, compilation and import passed. One existing dependency deprecation warning.
- `make infra-check`: generated Blueprint passed schema validation.
- `make container-build container-check infra-check`: stopped while Docker was
  still resolving pinned Python/uv base-image metadata. No new image or container
  check result is claimed. The independent infrastructure check above passed.
- No cloud deployment, credential changes, provider writes or external review
  were performed as part of this preparation.

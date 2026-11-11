# Live API and delivery evidence — 2026-11-11

**These are real API/delivery results, not deployed SLI calculations, Slack
receipt, rollback execution, or game-day evidence.** No credentials, Calendar
payloads or test event IDs are retained here.

## Independent API check

Maksym ran Leon's `verify_render.py` interactively against
`https://ospsd-team-2-5ogi.onrender.com` at **2026-11-11T03:57:21Z**.
[`consumer-verification.json`](consumer-verification.json) is the original
sanitized result: all **11** checks passed, including readiness, unauthenticated
403, authenticated missing-event 404, CRUD/read-back and deleted-event checks.
`test_event_cleaned_up` is true.

The script checks Event fields/time instants and missing-event errors, but its
`expected_release` field is a supplied label, **not a measured deployed SHA**.
This independent check must not be represented as #69 rollback/smoke execution.

## Successful canonical Delivery

[Run 43064300096](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/43064300096)
completed successfully at **2026-11-11T17:05:04Z**, source/workflow SHA
`7854d695cc2b8e84752ec3b4e4aacd2042125478`.
[`delivery.json`](delivery.json) was downloaded from its retained
`delivery-43064300096-1` artifact. It records:

- Exact published image digest and identified Render deployment.
- `platform: live`, `outcome: successful`, `smoke: passed`, `cleanup: confirmed`.
- `reconciliation_required: false`.
- An initial HTTP 400 before the digest-only fallback; the run ultimately passed.

This is a retained known-good candidate, not proof of the currently serving
release forever. Verify registry retention, environment/configuration
compatibility, and outstanding deployment reconciliation before using it for
rollback. No recovery/failure injection was performed by #72.

## Environment/approval check

[`environment-check.json`](environment-check.json) records the GitHub environment
API response checked at **2026-11-11T19:12:15Z**. `production` has no reported
protection rules; no `disposable` environment is listed. This snapshot does not
prove whether other manual safeguards or branch protections exist. The owner
must confirm the actual isolated exercise target and approval arrangement;
do not create an environment implicitly by dispatching a fault.

## Public Grafana observation

[`public-dashboard-check.json`](public-dashboard-check.json) retains sanitized
results from read-only public panel queries. The dashboard UID is
`team2-calendar-shared`, datasource `grafanacloud-prom`; Get traffic, categorized
errors and p95 series are returned. No credentials or configuration changes were
used. These fixed panel queries do not supply exact SLI counts.

For the recorded query ending **2026-11-11T21:04:26Z**, the latest returned Get
traffic/error points are **19:05Z**, and p95 is **18:50Z**. This is historical
telemetry, not proof of current export. Data still carries release `692597c`;
reconcile that identity with the later successful Delivery before interpreting
release-specific recovery. Do not infer either a current failure or current
health solely from these old points.

## Still missing

Protected collector/Prometheus/dashboard handoff, actual deployed source metrics
and history coverage, Slack firing/resolved receipt, independent responder and
approved window, actual recovery/runbook execution, postmortem and a completed
incident-driven follow-up. Neither the API check nor a green delivery supplies
these automatically.

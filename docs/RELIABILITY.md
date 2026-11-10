# Calendar reliability — DRAFT (#72)

Owner: Maksym Yemelianenko, Team 2. Operation: `GET /events/{event_id}`.

**Not deployed, not approved as an SLO, and not a completed game day.** This PR
provides candidate policy, rules, offline tests, and an operator handoff. No
notifications, live Calendar calls, deployment changes, or failures were triggered.

## Dependencies and release blockers

| Required input | Owner/dependency | Current status |
| --- | --- | --- |
| Restored design and conforming shared API | #65 / #67, release coordinator | This branch starts at `de8d392`; `DESIGN.md` and the shared package are absent after the revert. Do not interpret baseline tests as shared conformance. |
| Deployed metrics, actual query scope, dashboard URL and backend access | #70 / PR #73 | Rules use the reviewed metric schema at `3c7980a`. Telemetry is not in this branch and deployed access is unavailable. |
| Safe environment, runtime secrets, backend retention and permissions | #68 | No approved deployment URL, cloud access or isolated exercise environment supplied. |
| Immutable known-good artifact, exact rollback procedure and standard smoke check | #69 | Commands and recovery evidence are not available. Do not invent a second deployment path. |
| Approved alert channel and secret-mounted webhook | Team 2 coordinator | No real destination or receipt verification. The example channel and Grafana host are deliberate placeholders. |
| Initial measurements and consumer target approval | #72 with consumer/Team 2 review | Required before candidate targets can be treated as agreed. |
| Exercise window, independent responder and recorder | Team 2 | Not scheduled or assigned. The failure designer must not be the responder. |

All rows must be resolved before live acceptance. Docker is not running in the
implementation environment. Native rule/config validation does not prove a
backend is provisioned, a receiver works, or another person can recover service.

## Measurement and eligibility

Use the exact PR #73 operation label **`Get`**, not a URL or an event ID.
Metrics are measured by its HTTP middleware from entry to response completion.
The source instruments are `calendar_requests_total` and the classic histogram
`calendar_request_duration_seconds_{bucket,count}`. Histogram unit is seconds.

Eligible requests exclude outcomes `invalid_input`, `not_found`, and
`client_error`: rejected client input and ordinary missing resources are not
provider availability failures. All other outcomes are eligible. A successful
request has outcome `success` (PR #73 currently classifies HTTP < 400 this way);
configured-provider `access_denied`, `provider_error`, `provider_unavailable`,
and `application_error` are bad.
**Provider outages count against both objectives.** Do not change these exclusions
after an incident to improve the result.

Availability good events are eligible successful responses. Latency good events
are eligible **successful** responses completing within **1 second**, inclusive
(the existing `le="1"` bucket). Fast errors are not good latency events. Its
denominator comes from eligible histogram observations, not from success-only
traffic. Compare its denominator with the eligible request counter before
reporting: missing or unexplained mismatched observations make the report
incomplete, not silently successful.

Aggregate all releases in the window so a deployment does not reset the score.
The rules require a **Team-2-only backend/tenant for one environment**. PR #73 does not promise an
environment/service label on every metric: if the deployed backend mixes teams
or environments, agree and test its real bounded selector before loading these
rules. Never use resource IDs as metric labels. Multiple processes also need
PR #73's separate metric-stream identities before their counters can be trusted.

Limitations: completed server-side requests miss traffic that never reaches the
service, hangs that never complete, and telemetry lost during an exporter outage.
A wrong body with HTTP 200 can appear successful; conformance and the standard
smoke check must verify status/body independently; confirm redirects cannot
masquerade as successful fixture reads before adopting this policy. An unexpected
404 for an event that should exist can be hidden by the missing-resource
exclusion; the known-fixture
smoke check must detect that. No traffic or missing telemetry is **unknown**, not
100% reliability. A fresh deployment lacks a full history window.

## Candidate objectives and error budgets

| Objective | Candidate target | Window | Bad events permitted per 1,000 eligible requests |
| --- | --- | --- | --- |
| Availability | 99% successful | Rolling 24 hours | 10 |
| Successful response within 1 second | 95% | Rolling 24 hours | 50, including failed requests |

These are **planning assumptions, not evidence-based final commitments**. One
second is an existing histogram boundary and a proposed interactive-read budget;
it is not a measured production p95. The targets allow explicit, nonzero failure
budgets for the course service. Consumer needs and a live baseline must justify
or revise them before approval. PR #73's synthetic evidence includes a slow Get
fixture; it is not a clean live-provider latency baseline. Record the measurement,
tradeoff and approver here before marking the target criterion complete.

Recording rules live in `reliability/calendar.rules.yml`. Query at the same UTC
instant, in the approved scoped backend:

```promql
# Availability numerator and denominator
team2_calendar:get_success:increase24h
team2_calendar:get_eligible:increase24h
# Availability SLI
team2_calendar:get_success:increase24h / team2_calendar:get_eligible:increase24h

# Latency numerator and denominator
team2_calendar:get_fast_success:increase24h
team2_calendar:get_latency_eligible:increase24h
# Latency SLI
team2_calendar:get_fast_success:increase24h / team2_calendar:get_latency_eligible:increase24h
```

For each objective: `bad = denominator - numerator`,
`allowed_bad = denominator * (1 - target)`, and
`remaining_budget = allowed_bad - bad` (negative means exhausted). Prometheus
`increase` extrapolates counter samples, so counts may be fractional estimates.
Do not round before calculating the ratio. At low volume a single failure can
exhaust a budget: report counts alongside ratios. A zero/missing denominator has
no SLI; do not replace it with a successful score. Retain at least 24 hours of source
metrics and record actual coverage; a ten-minute sample is not a verified full day.

When either budget is exhausted with valid data, pause discretionary feature
rollouts, investigate the leading failure/latency category, and prioritize the
smallest reliability fix. The release coordinator may approve a recovery/security
change, with review, smoke verification and a rollback path. Resume ordinary
rollouts only after recovery and budget review. Unknown data requires a telemetry
check and a real smoke result, not an automatic healthy verdict.

## Alert configuration and handoff

`Team2CalendarGetHighFailureRate` detects **more than 20%** bad eligible Get
requests over five minutes, with **at least five** eligible requests, persisting
for two minutes. This short-window symptom alert is not the 24-hour SLO itself.
The minimum traffic guard avoids paging on one isolated request, but can miss an
outage on an idle service; inspect traffic and run the approved smoke check.
The alert clears when the condition stops. Old failures remain in the five-minute
window, so recovery notifications can lag recovery by that window plus evaluation
and notification intervals.

Before enabling anything, the #68/#70 owners must:

1. Confirm source metrics, backend isolation/stream identities, retention, and
   service release identity from the actual deployment.
2. Replace `GRAFANA_HOST.invalid` in the rules with the real absolute dashboard
   host. Ensure the runbook link is accessible to the responder and present at
   the deployed/reviewed revision.
3. Load the rule file into the existing Prometheus deployment, not a new backend.
4. Route alerts to the approved Alertmanager. Adapt
   `reliability/alertmanager.yml.example` to the actual Team 2 channel and mount
   the webhook URL at `/run/secrets/team2-calendar-slack-webhook` using protected
   runtime configuration. Do not commit the webhook or test it by posting secrets.
5. Preserve `send_resolved: true`. Check receipt of both firing and resolved
   messages with a real teammate. Config validation alone proves neither.

The Alertmanager example assumes a dedicated Team 2 instance. If it is shared,
merge a receiver/child route matched on `service="team2-calendar"`; do not replace
the existing root route or redirect other teams' alerts.

The examples are **not** provisioned by this PR. The webhook file does not exist
here, and the placeholder host is intentionally unroutable. Wiring rules,
receiver secrets and a protected backend belongs to the deployment/telemetry
owners; #69 should add `make reliability-check` to CI once tool versions are agreed.

## Runbook

Status: **draft, not independently exercised**. The exact #69 rollback/smoke
commands must be linked here before a responder can safely use this end to end.

**Symptom:** the alert above fires; Get is returning service/provider failures.

**Access:** Team 2 dashboard/log/trace read access; the approved disposable
service URL and designated timed test event; deployment/rollback permission for
that environment; a known-good artifact digest and approved rollback command.
Do not request or paste tokens, provider contents, private IDs or cloud secrets.

1. Confirm alert service, operation and environment. If scope is unclear, stop
   injection and contact the environment owner; never change another team's data.
2. Open `/d/team2-calendar` on the real Grafana host. Select **Get**, the UTC
   incident window, and relevant releases. Inspect categorized errors, traffic,
   latency and worker saturation. No series can mean telemetry failure.
3. Open a matching sanitized outcome log and its trace. Compare HTTP/provider
   spans and release identity. A provider span indicates an attempted call, not
   proof of a completed write. Never enable raw SDK/body debug logs.
4. Identify the last known-good immutable artifact via #69's release record.
   Use **the exact reviewed rollback command supplied by #69** in the approved
   disposable environment. **BLOCKED:** that command and target are not supplied
   yet. Do not substitute a guessed cloud command, bypass CI, or force a deploy.
5. Run **the same standard smoke check from #69**, not a weaker replacement.
   **BLOCKED:** its command/authentication/cleanup contract is not supplied yet.
   Confirm Get returns 200 with the expected Event; clean up any smoke-created
   resources using that procedure. Code rollback does not undo provider writes.
6. Confirm healthy request outcomes, recovering SLIs and the restored release.
   Wait for the five-minute failure window to clear, verify the real resolved
   notification, and record UTC timestamps and evidence links. If there is no
   traffic, use only the agreed safe workload; silence is not proof of recovery.
7. Remove the approved fault, stop test traffic, restore temporary configuration,
   and have #68 confirm disposable-resource cleanup/cost status. Do not destroy
   shared infrastructure. Escalate if the standard smoke check still fails.

## Game-day plan — NOT EXECUTED

Prerequisites: Levels 1–4 and shared conformance functional; normal smoke check
passes; SLO/threshold review complete; alert delivery already verified; exact
rollback procedure and known-good artifact available. No game day is authorized
by merely merging this draft.

Agree in writing: UTC window, environment owner/URL, permitted synthetic data,
workload rate within provider quota, reversible failure mechanism, designer,
**different responder**, and timeline recorder. Proposed mechanism: a reviewed
faulty artifact that makes only the safe Get path fail in a disposable environment.
Confirm with #69 that automatic smoke recovery will not clear it before the alert
can be observed. Do not disable pipeline protections; choose another approved
bounded scenario if necessary. Account for cached Get responses if caching is
restored. No credential revocation, production outage or data deletion is planned.

The designer must obtain explicit approval immediately before injection. Stop the
fault after **five minutes maximum**, or immediately on scope, privacy, data or
cost risk. Abort the exercise if unrecovered at 15 minutes and escalate; keep
recovery/cleanup staffed rather than abandoning a broken service. Safety help
from the designer is allowed if needed, but record that the independent-responder
criterion was then not met.

The recorder captures baseline smoke/SLIs → injection → alert firing/receipt →
responder diagnosis → rollback → identical smoke passing → alert resolution → SLI
recovery → cleanup. The responder follows the runbook without designer coaching.
Require a new explicit go/no-go before any fault; this PR contains no injection
script and triggers no deployment or notification.

## Evidence still required

Retain in the team's approved protected evidence location; link sanitized results
from #72. Do not fill these from unit-test fixtures or invent a postmortem.

| Evidence | Current result |
| --- | --- |
| Environment, release(s), UTC measurement window and actual coverage | NOT VERIFIED |
| Both numerators, denominators, SLI values and budget calculations | NOT VERIFIED |
| Approved targets, baseline evidence and consumer/reviewer rationale | NOT VERIFIED |
| Real alert destination; firing message receipt and UTC time | NOT VERIFIED |
| Recovery smoke run, alert resolution receipt and SLI recovery | NOT VERIFIED |
| Independent responder, recorder and incident timeline | NOT VERIFIED |
| Cleanup verification and resource cost confirmation | NOT VERIFIED |
| Blameless postmortem and completed follow-up | NOT VERIFIED |

After the actual exercise, write the postmortem with consumer/SLO impact,
detection/recovery timeline, trigger/contributing conditions, what helped/hindered,
and owned follow-ups. Complete and verify at least one justified follow-up before
the demonstration, linking its change and test/result. Pre-existing work is not
an incident-driven follow-up. Keep #72 open until external evidence is complete.

## Offline checks and references

Run the normal `make check`. Separately install compatible operator tools and run
`make reliability-check`; override `PROMTOOL` / `AMTOOL` with absolute executable
paths if needed. No server is started and no message is sent by these checks.

Validated locally with checksum-verified official **promtool 3.16.0** and
**amtool 0.35.0**, installed outside the repository. Match the eventual deployed
tool/backend versions and rerun before activation. These are operator tools, not
new application dependencies.

Native rule tests cover eligibility, fast-success latency (not fast failures),
permission/provider failures, pending/firing/clearing, low traffic, missing data,
release aggregation and counter resets. They simulate rule evaluation only, not
real alert transport or an infrastructure recovery.

- [PR #73 metric schema and limitations](https://github.com/Airbus-A330/OSPSD-Team-2/blob/3c7980a54b01bf302b5fff8177365559353fb3ca/docs/OBSERVABILITY.md)
- [Prometheus rule tests](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- [Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/)

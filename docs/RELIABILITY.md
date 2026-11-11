# Calendar reliability (#72)

Owner: Maksym Yemelianenko. **End-to-end work in progress**, not completed Level 4
or game-day evidence. I own integrating, measuring, configuring/testing the alert,
verifying the runbook and completing the exercise with teammates; this document
is not a substitute for those executions.

## Agreed policy and measurement

[Alexander's direction](https://github.com/Airbus-A330/OSPSD-Team-2/pull/74#issuecomment-6757433749),
with his [bucket clarification](https://github.com/Airbus-A330/OSPSD-Team-2/pull/73#issuecomment-6757791352),
sets **Get availability 99%; latency 95% at <=1 second; both rolling 7 days**.
These replace the earlier 24-hour candidates. Keep the one-second threshold
unless actual measurements clearly justify a change. The rationale is
the team's interactive-read requirement with explicit nonzero budgets, not an
industry guarantee or a claim of observed production performance.

| Item | Definition |
| --- | --- |
| Representative operation | `GET /events/{event_id}`, telemetry operation **`Get`** |
| Eligible events, both SLIs | Syntactically valid GET requests reaching the service; exclude HTTP **400/422** (`invalid_input`) only |
| Availability good | HTTP **200** and **contract-correct 404** |
| Availability bad | Eligible responses other than those above; **403/502/503** provider failures count, as do other unexpected eligible statuses |
| Latency good | Eligible GETs in the 1-second bucket, including 404; the availability objective independently counts fast provider failures as bad |
| Measurement | PR #73 HTTP middleware, entry through response completion; seconds, not milliseconds |
| No traffic / missing telemetry | Unknown/no-data, never 100% healthy |

### Actual producer interface and fidelity limits

The rules integrate against merged telemetry #73 and hosting #75, together on
[`692597c`](https://github.com/Airbus-A330/OSPSD-Team-2/tree/692597cc799b2f5e640c142eee6986106c92a848).
The [telemetry interface](OBSERVABILITY.md#signal-schema-and-level-4-handoff) remains:
`calendar_requests_total`, `calendar_request_duration_seconds_bucket` / `_count`,
with `operation`, `outcome`, and `release`. Invalid input combines 400/422;
`not_found` represents 404. Other client errors remain eligible, not excluded.

Status classification and the bucket boundary now match the agreed policy:

- Get `success` is **exact HTTP 200**. Unexpected 2xx/3xx become
  `unexpected_status` and count as availability failures. Availability good
  remains `success|not_found` (200 + contract-correct 404).
- The `le="1"` bucket is **upper-inclusive**: <=1 second, not strict <1.
  Alexander explicitly confirmed this interpretation; no stricter bucket is
  required. The query cannot distinguish an exactly-one-second event.

Counters cannot verify an Event/error body. A contract-broken 404 or unexpected
404 for a known existing fixture can appear good; shared conformance and the
standard known-fixture smoke check must verify status/body independently.
Completed server-side requests also miss upstream failures, never-completing
requests and lost exporter data. Check exporter health and actual history.

#68 now selects Render Free with ephemeral storage; see its
[deployment procedure](https://github.com/Airbus-A330/OSPSD-Team-2/blob/f7d60dc458d687870e3c80f2e3c4b5483d9076a2/docs/DEPLOYMENT.md).
Sleeping instances can add cold-start delay before a request reaches middleware.
Keep the agreed <=1s objective, but report that server-side measurements do not
establish end-to-end cold-start availability or latency. Record cold-start smoke
results separately; do not silently exclude observed slow eligible requests.

Aggregate releases so deployment does not reset the budget. These rules require
one Team 2 environment's backend/tenant. For a mixed backend, first apply and
test its actual service/environment selector. Multiple workers/replicas need
PR #73's separate stream identities; do not merge colliding cumulative counters.
Never label metrics with URLs, private event IDs, request IDs or tokens.

## Queries, report and budgets

`reliability/calendar.rules.yml` supplies the following recording rules. Run all
at one UTC instant in the correctly scoped backend:

| Quantity | Availability | Latency |
| --- | --- | --- |
| Numerator | `team2_calendar:get_good:increase7d` | `team2_calendar:get_fast:increase7d` |
| Denominator | `team2_calendar:get_eligible:increase7d` | `team2_calendar:get_latency_eligible:increase7d` |
| Current SLI | `team2_calendar:get_availability:ratio7d` | `team2_calendar:get_latency:ratio7d` |
| Allowed bad events | `team2_calendar:get_availability_allowed:budget7d` | `team2_calendar:get_latency_allowed:budget7d` |
| Remaining bad-event budget | `team2_calendar:get_availability_remaining:budget7d` | `team2_calendar:get_latency_remaining:budget7d` |

Export all ten values with one read-only Prometheus API query:

```sh
make reliability-report PROMETHEUS_URL=https://YOUR_APPROVED_PROMETHEUS_HOST
```

The target uses `curl`, a 30-second timeout and one UTC evaluation timestamp.
Supply required authentication through approved protected curl configuration,
not credentials in the URL, Make arguments or committed files. A non-2xx response
fails explicitly. Preserve the JSON, query source revision, backend scope, source
release(s), evaluation timestamp and actual history coverage in sanitized evidence.
Each returned sample contains the evaluation Unix timestamp `t`; the configured
window is `(t - 604800, t]`. Empty results or absent ratios mean **unknown**, not a
successful run; a zero denominator suppresses the corresponding ratio.

Compare the request and histogram denominators; unexplained discrepancies make
the report incomplete. Retain at least 7 days of source data. A newly deployed
backend can calculate a 7-day-lookback query over seconds of history: that is not
7-day coverage. Exporter gaps still need investigation even with old samples.

For each objective: `bad = denominator - numerator`,
`allowed_bad = denominator * (1 - target)`,
`remaining_budget = allowed_bad - bad`. Per **1,000** eligible requests the
availability budget is **10** and latency budget **50**. Negative means overspent;
zero means no budget remains. `increase` extrapolates, so counts/budgets can be
fractional estimates. Keep unrounded values. A single low-volume failure can
exhaust a budget; show counts as well as ratios.

**Error-budget policy:** if either valid-data budget is exhausted, pause
nonessential feature/deployment work and prioritize reliability fixes until
recovery. Reviewed recovery/security changes may proceed with smoke verification
and a known-good rollback path. Resume discretionary changes only after service
recovery and budget review with the coordinator. Unknown data requires a telemetry
check and real smoke result, not an automatic healthy verdict.

## Alert and activation

`Team2CalendarGetHighFailureRate`: **>20%** bad eligible Get requests over 5 minutes,
**>=5** eligible requests, persisting **2 minutes**, evaluated every minute.
Good 404s do not spend its failure budget. This short-window user-symptom alert is
not itself the 7-day SLO. Its low-traffic guard can miss an idle-service outage.
Old failures can delay resolution by the five-minute lookback plus evaluation and
notification intervals. A seven-day SLI also retains incident failures after
recovery: show healthy new traffic and stopped budget consumption, not an
instantaneous return to 100%.

Activation steps owned by #72, coordinated with #68/#69/#70:

1. Confirm deployed source names, scope/stream identities, retention and immutable
   `CALENDAR_RELEASE`. Configure protected `OTEL_EXPORTER_OTLP_ENDPOINT` and any
   required authentication/certificates per [OBSERVABILITY.md](OBSERVABILITY.md).
   Without that endpoint, the app emits console logs but exports no metrics/traces.
   Merged #75 now composes the base lifespan and instruments early access-denied
   responses. Local hosted integration checks this boundary; verify actual hosted
   exports and collector connectivity before trusting a deployment.
2. Replace `GRAFANA_HOST.invalid` in the rule and matching test expectation with
   the actual dashboard host. Confirm responder access to dashboard and runbook.
3. Load the rules into the team's existing protected Prometheus, with an
   Alertmanager route. Do not create an alternative infrastructure stack.
4. Adapt `reliability/alertmanager.yml.example` for the **Team 2 Slack channel**.
   Mount the webhook at `/run/secrets/team2-calendar-slack-webhook` through the
   protected runtime configuration. Email is a fallback only if Slack cannot work.
   No webhook/token belongs in Git, command history or ordinary artifacts.
5. Preserve `send_resolved: true`. Deliberately trigger only in an approved safe
   environment; have a teammate verify both firing and resolved receipt.

The example assumes a dedicated Team 2 Alertmanager. For a shared instance,
merge a receiver/child route matched on `service="team2-calendar"`; do not replace
its root route or redirect other teams' alerts. No example is provisioned or
connected to a real destination by this branch yet.

## Runbook

**Symptom:** eligible Get failures trigger the alert above. **Access:** protected
Grafana/Prometheus, sanitized logs/traces, approved disposable service, deployment
permission, known-good immutable artifact, and the standard #69 smoke check.

1. Check service/environment and UTC alert window. Stop injection and contact the
   environment owner immediately if scope, data, privacy or cost is uncertain.
2. Open the real Grafana `/d/team2-calendar`, select **Get**, time and releases.
   Inspect traffic, categorized failures, latency and saturation. Run the report
   above for counts/SLIs/budgets. No series can mean telemetry failure.
3. Follow a sanitized outcome log's trace to its HTTP/provider spans. Compare
   timings and release identity. Never enable SDK/body/raw-URL debug capture.
4. Restore the last known-good artifact using **#69's approved rollback path**.
   #68's current foundation is one Render Free image-backed service/Blueprint,
   with protected bearer access and no persistent disk. Preserve service identity
   and keep the Blueprint's image reference consistent with the restored image.
   Startup reconstructs the disposable OAuth cache from protected runtime secrets;
   do not depend on a token file surviving rollback or restore stale credentials.
   Code rollback does not undo Google writes or token/config changes.
   Follow [DELIVERY.md#rollback](DELIVERY.md#rollback): pause merges and reconcile
   running/pending deliveries; dispatch **Delivery** on `assgn2-ms3-submission`
   with the retained `image` digest and explicitly approved `target`. Do not
   rebuild it. A successful retained [delivery artifact](evidence/reliability-live/README.md)
   now identifies a known-good candidate; confirm it is still appropriate for the
   selected environment before dispatch. No rollback has been executed by #72.
5. Run **the identical #69 deployment consumer/smoke check**, not a weaker new
   script. Confirm expected Event 200 and contract-correct missing-event 404.
   `/readyz` is provider-independent and cannot replace the real smoke check.
   The same Delivery workflow calls `scripts.smoke_calendar.smoke_calendar`
   automatically: bounded five-minute readiness wait, real CRUD and confirmed
   cleanup, with no write retries. Require its retained artifact to say
   `outcome: successful`, `smoke: passed`, `cleanup: confirmed`.
   The separately run teammate verification script proves API behavior, not an
   execution of this recovery procedure. Never expose protected runtime tokens.
6. Confirm restored release, healthy new Get outcomes, improving short-window
   results and stopped error-budget burn. Verify the alert's resolved receipt.
   Continue only the approved safe workload; silence is not recovery evidence.
7. Remove the fault, restore temporary configuration, stop test traffic and
   perform the standard smoke cleanup. Have #68 confirm disposable-resource/cost
   cleanup. Never destroy shared infrastructure. Escalate persistent failures.

Status: not independently exercised. Exact recovery inputs must be filled before
claiming another teammate can follow this runbook end to end.

## Game day — execution pending

Run only after Levels 1–4/conformance, normal deployment smoke and real alert
transport work. Use a **bounded faulty deployment** affecting Get in Team 2's
own disposable environment, synthetic data only. Obtain explicit approval before
injection; merging this work is not that approval.

Agree and record UTC window, owner/environment, workload/quota, known-good and
faulty digests, rollback, scope and cleanup. Assign **three separate teammates**:
failure designer, independent responder, and incident recorder. Maksym owns the
failure design/coordination; Airbus is the timeline recorder per his
[confirmation](https://github.com/Airbus-A330/OSPSD-Team-2/pull/74#issuecomment-6771935361).
The independent responder and approved execution window remain unassigned.
Coordinate with #69 so pipeline safeguards remain enabled; do not
disable smoke protection to prolong an alert. Account for cached Get responses.
The startup-crashing image in #69's delivery exercise is not automatically a
valid #72 alert trigger: Render may retain the healthy old instance, yielding no
Get failures. Verify that the separately approved fault actually produces the
agreed user-visible symptom; do not equate a failed deployment with alert delivery.

Stop the fault after **5 minutes maximum**, or immediately on unintended impact.
If unrecovered at 15 minutes, abort/escalate and keep recovery/cleanup staffed.
Safety help is allowed, but then record that unassisted recovery was not met.

The recorder retains: baseline smoke/SLIs → injection → alert firing/receipt →
responder dashboard diagnosis → runbook rollback → identical smoke passing →
resolved receipt → SLI recovery/stopped burn → cleanup. No designer coaching.
Write a blameless postmortem with consumer/SLO impact, detection/recovery timeline,
trigger/contributing factors, what helped/slowed recovery, and explicitly owned
follow-ups. Complete and verify **at least one incident-driven follow-up** before
the demonstration, with linked change/result. Pre-existing work is not that action.

## Execution status and checks

- Rules, calculations, receiver config and native test scenarios: implemented.
- Native tools also run in the **Format** workflow via `make reliability-check`.
- [Original local producer capture](evidence/reliability-local/README.md): historical
  synthetic-route check, retained with its original provenance.
- [Merged hosted integration](evidence/reliability-hosted-local/README.md): actual
  hosted factory/shared Get/provider translation, 24 HTTP requests and 18
  SDK-controlled calls through OTLP to all ten SLI/budget metrics. Seven automated
  hosted metric regressions are included in `make check`. This remains local,
  not deployed Google verification or a completed alert/game-day exercise.
- #73 telemetry and #75 hosting are merged in `assgn2-ms3-submission@692597c`;
  hosted startup/shutdown and early access rejection are no longer code blockers.
  Hosting uses Render Free with ephemeral credential storage and no disk.
- Hosting/deployment setup: Leon with Airbus. Capture the final service URL,
  workspace/service owner, release/image digest and protected workflow access
  from their deployed handoff; chat setup progress is not live acceptance evidence.
- #69/#78 and diagnostics #79 are merged in `assgn2-ms3-submission@7854d69`.
  Dorien's [delivery/rollback procedure](DELIVERY.md) is available. Successful
  Delivery run `43064300096` retains a published digest, live platform result,
  passing real smoke and confirmed cleanup. It is not rollback/game-day evidence.
- [Live API evidence](evidence/reliability-live/README.md): Maksym independently
  ran Leon's 11-check script and confirmed cleanup. Its `expected_release` field
  is not a measured deployed SHA; the later Delivery artifact has separate provenance.
- Game-day environment safety remains pending: GitHub currently lists `production`
  without required-reviewer rules and no `disposable` environment. Airbus and the
  delivery/environment owner must confirm target isolation and approval controls
  before any fault/rollback dispatch; this branch does not configure them.
- Protected collector/backend/dashboard access and history: Nicolas with Airbus.
  Current live SLI/budget records and real export verification remain pending.
- Alert destination: Team 2 Slack, protected provisioning coordinated by Airbus.
  Designer/coordinator: Maksym; recorder: Airbus; independent responder: TBD.
- Real Slack configuration, deliberate alert delivery/resolution, actual rollback,
  independent runbook exercise and full game day: pending. The smoke/rollback
  implementation is present; execution approval/access is a separate requirement.
- Postmortem, one completed verified follow-up and retained live submission
  evidence: pending. **Keep #72 open; continue integration as dependencies land.**

Run `make check` and `make reliability-check`. The latter uses checksum-verified
**promtool 3.16.0** and **amtool 0.35.0**, not new application dependencies.
Override `PROMTOOL`/`AMTOOL` with absolute executable paths locally. Recheck against
the eventual deployed versions. No check sends a Slack message or injects a fault.

References: [rule tests](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/),
[alert rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/),
[Alertmanager](https://prometheus.io/docs/alerting/latest/configuration/).

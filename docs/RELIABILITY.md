# Calendar reliability (#72)

Owner: Maksym Yemelianenko. **Implementation and API verification are complete;
exact live SLI/budget capture, real alert delivery and game-day acceptance remain
pending.** Preparing files is not evidence that the exercise happened.

## Agreed policy and measurement

[SLI/SLO definitions, eligibility, measurement location, targets and limitations](reliability/sli-slo.md)
are canonical. [Error-budget policy](reliability/error-budget-policy.md) defines
what Team 2 pauses/prioritizes when either budget is exhausted.

## Queries, report and budgets

[Exact source queries, current-value table and calculations](reliability/sli-slo.md#capture-the-exact-live-values).
Import the small [measurement dashboard](reliability/measurement-dashboard.json)
in the existing Grafana stack to retrieve the four source counts at one instant.
This does not require new recording rules or another backend.

When recording rules are loaded, use `make reliability-report` against the
approved protected Prometheus query endpoint. The existing public dashboard
verifies traffic/error/latency series, not exact SLI counts or full history.

## Alert and activation

[Alert condition, destination setup, no-data behavior and delivery verification](reliability/alerting.md).
The native rule now links to the real public dashboard. Airbus approved email as
an alternative to Slack; contact-point setup and real firing/resolved receipts
still need execution. No real message is sent by the repository checks.

## Runbook

[Canonical responder runbook](reliability/runbook.md): symptom, access, likely
causes, diagnostic queries, safe recovery, standard smoke/cleanup and limitations.
This stable index preserves the existing alert's `docs/RELIABILITY.md#runbook`
link. Do not create a separate deployment path or weaken #69's checks.

## Game day — execution pending

Run only after required Levels 1–4/conformance, normal deployment smoke and real
alert transport work. Use one **bounded faulty deployment** affecting Get in
Team 2's explicitly approved disposable service/calendar, synthetic data only.
Merging code is not approval to inject a failure.

Agree and record UTC window, service/workspace owner, workload/quota, source and
known-good/faulty digests, rollback, scope and cleanup. Latest coordinator chat:
Maksym designs/coordinates the failure; Airbus volunteered to respond and record.
The responder must not design the fault. [#72](https://github.com/Airbus-A330/OSPSD-Team-2/issues/72)
also says **another participant records the timeline**; confirm a separate
recorder or explicitly resolve that criterion before claiming completion.
The window and actual environment approval remain unrecorded here.

Coordinate with #69 so safeguards remain enabled. Do not disable smoke protection
to prolong an alert; account for cached Get responses. #69's startup-crashing
image is not automatically an appropriate alert trigger: Render can keep an old
healthy instance serving, producing no Get failures. Verify the approved fault
actually creates the intended user-visible symptom.

Stop injection after **5 minutes maximum**, or immediately if scope escapes,
credentials/privacy/cost are at risk, cleanup is unbounded, or recovery is unsafe.
If unrecovered at **15 minutes**, abort/escalate and keep recovery/cleanup staffed.
Safety help is allowed, but disclose that unassisted recovery was not met.

Airbus owns the actual `game-day.md` and evidence collection: baseline -> injection
-> firing/receipt/acknowledgement -> dashboard/log/trace diagnosis -> mitigation
-> restored release -> canonical smoke/cleanup -> resolved receipt -> healthy
new traffic/stopped budget burn -> cleanup. Link his files when present; do not
fabricate or duplicate a timeline. No designer coaching beyond safety intervention.

Use the [postmortem template](reliability/postmortem.md) after execution. Include
consumer/SLO impact, trigger/contributing conditions, what helped/slowed recovery,
and owned follow-ups. Complete and verify at least **one incident-driven action**
before claiming extra credit. Pre-existing work is not that action.

## Execution status and checks

- Rules, calculations, native scenarios, receiver example and hosted metric
  regressions: implemented; native tools run in Format CI.
- [Original synthetic-route capture](evidence/reliability-local/README.md) and
  [actual hosted SDK-controlled OTLP capture](evidence/reliability-hosted-local/README.md)
  retain exact provenance. Neither is deployed SLO/game-day evidence.
- [Live API/delivery evidence](evidence/reliability-live/README.md): Maksym's
  11-check independent API run passed with cleanup; canonical Delivery run
  `43064300096` succeeded with real smoke and confirmed cleanup. The API script's
  `expected_release` is a label, not independently measured release identity.
- #73/#75/#76/#78/#79 are integrated. Canonical [delivery/rollback](DELIVERY.md)
  implementation and a retained known-good digest candidate are available.
  The [reported ID-less digest fallback edge](https://github.com/Airbus-A330/OSPSD-Team-2/issues/69#issuecomment-6804954356)
  still needs owner resolution/reconciliation before reliance on that path.
- Nick/Leon report Cloud ingestion works; public API queries independently return
  Get traffic, errors and p95. [Public check](evidence/reliability-live/public-dashboard-check.json)
  is observational evidence, not exact SLI calculation or private query access.
- Public series still carry release `692597c`; successful later Delivery identifies
  source `7854d69`. Ask the owner to reconcile `CALENDAR_RELEASE` with the actual
  serving image; historical series alone do not prove a current misdeployment.
- Protected Grafana invite was sent to Maksym per team chat. Import the measurement
  view and capture its four unrounded source values/time; exact SLIs/budgets and
  actual history coverage remain pending, not blocked on missing exporter code.
- The retained environment snapshot lists production with no protection rules
  and no disposable environment. It does not prove other manual controls are
  absent. Confirm actual target isolation and approval before any dispatch.
- Real email/Slack receipt and resolution, runbook exercise, fault/rollback,
  postmortem and completed verified follow-up: pending. **Keep #72 open.**

Run `make check` and `make reliability-check`. Native tools are checksum-verified
**promtool 3.16.0** and **amtool 0.35.0**; override `PROMTOOL`/`AMTOOL` with local
absolute paths and recheck against deployed versions. Docker/runtime and cloud
permissions are separate from these local checks.

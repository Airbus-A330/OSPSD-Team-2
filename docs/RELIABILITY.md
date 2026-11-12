# Calendar reliability (#72)

Owner: Maksym Yemelianenko. **Implementation, live SLI/budget measurement, bounded game-day execution, recovery documentation, and postmortem evidence are recorded. Alert-delivery status is documented from the actual exercise and is not inferred from configuration alone.** Preparing files is not evidence that the exercise happened.

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

## Game day

Team 2 completed a bounded reliability game day using temporary fault branch
`game-day`.

Fault revision:

`6ab6f25bd2fe4e6ce2d6f5959ad3e522452cb653`

The fault caused valid shared Get requests to return
`503 provider_unavailable` through the normal service error and telemetry path
while preserving the service process, health endpoints, metrics, structured
logs, and traces.

The exercise used bounded controlled traffic, the existing public Grafana
dashboard, the responder runbook, and the existing immutable Delivery rollback
path.

The deliberately faulty implementation remained isolated from
`assgn2-ms3-submission`.

The complete execution record is in:

- [game-day.md](reliability/game-day.md)
- [postmortem.md](reliability/postmortem.md)
- [alerting.md](reliability/alerting.md)
- [runbook.md](reliability/runbook.md)

The exercise record contains the actual deployment/traffic/recovery evidence,
the independent responder result, the dashboard/alert observations, and the
completed incident-driven follow-up.

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
- The imported measurement view now has a [live screenshot observation](reliability/sli-slo.md#capture-the-exact-live-values):
  availability approximately 72.88% (budget exhausted), latency approximately
  98.31%, source age 4.16s. These use rounded displayed counts; raw precision,
  exact query timestamp and full history coverage are not verified. Do not call
  green panels proof of meeting both SLOs.
- The retained environment snapshot lists production with no protection rules
  and no disposable environment. It does not prove other manual controls are
  absent. Confirm actual target isolation and approval before any dispatch.
- Real email/Slack receipt and resolution, runbook exercise, fault/rollback,
  postmortem and completed verified follow-up: pending. **Keep #72 open.**

Run `make check` and `make reliability-check`. Native tools are checksum-verified
**promtool 3.16.0** and **amtool 0.35.0**; override `PROMTOOL`/`AMTOOL` with local
absolute paths and recheck against deployed versions. Docker/runtime and cloud
permissions are separate from these local checks.

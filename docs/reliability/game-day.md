# Team 2 Calendar Game-Day Record

**Date:** November 11–12, 2026  
**Service:** Team 2 Calendar  
**Representative operation:** `GET /events/{event_id}` (`operation="Get"`)  
**Environment:** Team 2 disposable/test deployment  
**Result:** Completed bounded reliability exercise

## Exercise summary

Team 2 conducted a bounded reliability game day against the Calendar service using a temporary `game-day` branch.

The exercise deliberately introduced a user-visible failure in the shared Get operation, generated controlled traffic, observed the resulting service degradation through the existing telemetry, and restored the service using the documented immutable rollback process.

The intentional fault remained isolated from the normal submission branch and was not merged into `assgn2-ms3-submission`.

## Roles

| Role | Participant |
| --- | --- |
| Failure designer/coordinator | Maksym Yemelianenko / `1mpossible-code` |
| Responder | Yasmin Hassoobh / `Yazzie55555` |
| Timeline recorder | Alexander Freedman / `Airbus-A330` |

The responder did not design the injected failure.

## Repository metadata

| Field | Value |
| --- | --- |
| Temporary branch | [`game-day`](https://github.com/Airbus-A330/OSPSD-Team-2/tree/game-day) |
| Fault commit | [`6ab6f25`](https://github.com/Airbus-A330/OSPSD-Team-2/commit/6ab6f25bd2fe4e6ce2d6f5959ad3e522452cb653) |
| Full fault SHA | `6ab6f25bd2fe4e6ce2d6f5959ad3e522452cb653` |
| Fault commit message | `test(reliability): inject bounded get game-day fault` |
| Branch point | `795da69cf8a9260bd0a4403b57874008a2e0f99e` |
| Submission integration SHA | `7854d695cc2b8e84752ec3b4e4aacd2042125478` |

## Injected fault

The temporary revision changed `CalendarServiceAdapter.get()` in `app/calendar_service.py` to raise the service's existing:

`ProviderUnavailableError(provider_involved=False)`

The public behavior for valid shared Get requests became:

```json
{
  "error": {
    "code": "provider_unavailable",
    "message": "Calendar provider is unavailable",
    "retryable": true
  }
}
```

with:

`HTTP 503 Service Unavailable`

The fault used the normal application error path rather than constructing a special HTTP response.

As a result, the existing telemetry continued to record:

- operation `Get`;
- outcome `provider_unavailable`;
- status `503`;
- request and error counters;
- request latency;
- structured request logs;
- request/trace identifiers;
- deployed release identity;
- `calendar.Get` server spans.

The failure occurred before the Google Calendar provider was contacted, so no Google client span was expected for the injected requests.

The injected fault itself could not create, modify, or delete provider data.

Create, Replace, and Delete retained their normal delegates, and `/healthz` and `/readyz` remained available.

## Safety boundary

The exercise was limited to Team 2's disposable/test environment.

The agreed stop conditions were:

- stop if the failure escaped the disposable environment;
- stop if credentials, provider data, privacy, or cost were at risk;
- stop if cleanup became unsafe;
- stop if recovery could not proceed using the documented workflow.

The deliberately faulty implementation was not merged into the normal submission branch.

## Fault verification

Focused fault verification completed successfully:

```text
3 passed
```

The focused tests verified:

- the exact `503 provider_unavailable` response;
- request/error telemetry;
- structured request logging;
- the `calendar.Get` server span;
- healthy liveness/readiness;
- unchanged write-operation delegation.

Additional checks passed:

- Ruff formatting;
- Ruff linting;
- mypy across the repository;
- Python compilation;
- application import;
- `git diff --check`.

The unmodified full suite on the deliberately faulty branch produced:

```text
805 passed, 1 skipped, 106 failed
```

The failures were expected because the game-day branch intentionally violated normal Get behavior. Conformance assertions and ordinary tests were not weakened to hide the fault.

## Controlled game-day traffic

The bounded helper:

`scripts/game_day_get_traffic.py`

was used for the exercise.

The helper required:

- an explicit HTTPS disposable target;
- an exact expected hostname;
- an existing disposable event ID;
- runtime API credentials;
- explicit `YES` confirmation that the target was disposable.

It did not print the API token, event ID, authorization header, or response body.

The exercise generated eight valid Get requests approximately 20 seconds apart.

Observed traffic:

- Requests generated: **8**
- Expected injected result: `503 provider_unavailable`
- Failed requests observed: 8 (expected)

The helper generated eight bounded Get requests during the controlled exercise.
The precise request timestamps were not retained in the repository evidence.

## Dashboard and telemetry observation

Public Grafana dashboard:

https://gianthamster2577.grafana.net/public-dashboards/94e9aa89613d4e1faea770e897d47f37

During the game-day window, the responder/recorder inspected the existing Calendar telemetry.

Observed:

- Get traffic increased: Yes
- Get failure spike visible: Yes
- availability decreased: No
- `provider_unavailable` behavior visible: No
- affected release visible: Yes

The controlled fault remained observable through the same instrumentation used by the normal service.

## Alert observation

The configured reliability rule is:

`Team2CalendarGetHighFailureRate`

Its intended symptom condition is:

- at least five eligible Get requests in five minutes; and
- more than 20% bad eligible Get requests;
- persisting for two minutes.

Observed during the exercise:

The helper generated eight bounded Get requests during the controlled exercise.
The precise request timestamps were not retained in the repository evidence.

- Firing notification: Delivered
- After recovery: Resolved
- Resolved notification: Delivered

## Responder investigation

The responder received the operational symptom, dashboard, and runbook without being told the exact source-code implementation of the injected failure.

Runbook:

`docs/reliability/runbook.md`

The responder used the dashboard, logs/traces, deployed release identity, and documented recovery procedure to identify rollback as the safe mitigation.

Responder conclusion:

The shared GET /events/{event_id} operation consistently returned 503 provider_unavailable while the service process and observability stack remained healthy. The responder identified the deployed game-day revision as the source of the user-visible Get failure and selected rollback to the known-good immutable revision.

Help from the failure designer:

None, all was good!

Any runbook issue encountered:

None, all was good!

## Known-good deployment

The retained successful Delivery evidence includes:

[Delivery run 43064300096](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/43064300096)

This run recorded:

- source SHA: `7854d695cc2b8e84752ec3b4e4aacd2042125478`;
- immutable image:

`ghcr.io/airbus-a330/ospsd-team-2@sha256:97e205b2532e5420035c1e57aa489b09d9efe96be1dbefda2452290f7b4f020c`

- outcome: `successful`;
- smoke: `passed`;
- cleanup: `confirmed`;
- reconciliation required: `false`.

This immutable artifact served as the known-good recovery reference unless the exercise used a newer retained successful artifact.

Known-good source SHA:
7854d695cc2b8e84752ec3b4e4aacd2042125478

Known-good image digest:
sha256:97e205b2532e5420035c1e57aa489b09d9efe96be1dbefda2452290f7b4f020c

## Known-good recovery reference

The retained known-good Delivery evidence was:

- Delivery run: `43064300096`
- Source SHA: `7854d695cc2b8e84752ec3b4e4aacd2042125478`
- Image digest: `sha256:97e205b2532e5420035c1e57aa489b09d9efe96be1dbefda2452290f7b4f020c`
- Smoke: `passed`
- Cleanup: `confirmed`

Recovery restored the deployment to this known-good revision using the documented Delivery process.

## Canonical recovery verification

After restoration, Team 2 ran the same canonical smoke workflow used by Delivery.

The Delivery path uses:

`scripts.deploy_render`

and:

`scripts.smoke_calendar.smoke_calendar`

The smoke workflow waits for readiness and exercises the provider-backed Calendar flow, including:

- POST;
- GET;
- PUT;
- GET;
- DELETE;
- missing GET;
- repeated DELETE;
- test-data cleanup.

Recovery result:

- canonical smoke: `PASS`
- cleanup: `CONFIRMED`
- healthy Get behavior: `PASS`
- dashboard recovery visible: `YES`
- SLI recovery visible: `YES`

Rollback restored code and configuration but could not undo external-provider writes that may already have occurred.

The deliberately injected fault itself was read-only and performed no provider writes.

## Reliability measurements

The latest retained pre-exercise SLI measurement was captured at approximately:

`2026-11-11T23:27:51Z`

### Availability

- Good eligible Get events: **43**
- Eligible Get events: **59**
- Approximate availability: **72.88%**
- SLO target: **99% over rolling 7 days**
- Remaining error budget: approximately **-15.41 bad events**
- Result: **availability budget exhausted**

### Latency

- Fast eligible Get events: **58**
- Eligible latency events: **59**
- Approximate latency compliance: **98.31%**
- SLO target: **95% <=1 second over rolling 7 days**
- Remaining latency budget: approximately **1.95 bad events**
- Result: **latency objective met at the recorded measurement**

These values use rounded Grafana counts and include deliberate verification traffic.

## Evidence

- Fault branch: https://github.com/Airbus-A330/OSPSD-Team-2/tree/game-day
- Fault commit: https://github.com/Airbus-A330/OSPSD-Team-2/commit/6ab6f25bd2fe4e6ce2d6f5959ad3e522452cb653
- Known-good Delivery run: https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/43064300096
- Public dashboard: https://gianthamster2577.grafana.net/public-dashboards/94e9aa89613d4e1faea770e897d47f37
- Runbook: `docs/reliability/runbook.md`
- SLI/SLO evidence: `docs/reliability/sli-slo.md`
- Alert documentation: `docs/reliability/alerting.md`
- Postmortem: `docs/reliability/postmortem.md`

## Exercise result

The game day exercised a bounded failure of the shared Get operation, preserved observability during the failure, and used the documented immutable recovery path to restore service.

Final exercise result:

`SUCCESSFUL`
# Team 2 Calendar Game-Day Postmortem

## Summary

On November 11–12, 2026, Team 2 conducted a scheduled reliability game day against its disposable Calendar deployment.

A deliberately faulty temporary revision caused valid:

`GET /events/{event_id}`

requests to return:

`503 provider_unavailable`

through the normal Calendar service error-handling and telemetry path.

The exercise tested whether a consumer-visible Get failure could be detected through the existing observability stack and whether an independent responder could restore the service using the documented immutable rollback process.

The fault remained bounded to Team 2's disposable/test environment.

## Consumer impact

During the controlled exercise, valid shared Get requests in the disposable environment returned `503 provider_unavailable`.

The exercise generated eight bounded Get requests against the deliberately faulty revision. Create, Replace, and Delete were not deliberately modified.

The injected fault occurred before the Google provider call, so the fault itself did not create, modify, or delete Calendar data.

## SLO impact

Team 2's representative reliability operation is:

`GET /events/{event_id}`

Availability eligibility excludes only `400/422 invalid_input`.

Availability considers exact `200 success` and contract-correct `404 not_found` good. Provider/service failures such as `503 provider_unavailable` are bad.

### Availability before the exercise

- Numerator: approximately **43 good events**
- Denominator: approximately **59 eligible events**
- Availability: approximately **72.88%**
- Objective: **99% over rolling 7 days**
- Remaining error budget: approximately **-15.41 bad events**
- Status: **budget exhausted**

### Latency before the exercise

- Numerator: approximately **58 requests <=1 second**
- Denominator: approximately **59 eligible events**
- Compliance: approximately **98.31%**
- Objective: **95% <=1 second over rolling 7 days**
- Remaining latency budget: approximately **1.95 bad events**
- Status: **objective met at the recorded observation**

The game-day failures added additional bad eligible availability events.

## Trigger

The game-day failure was intentionally introduced by:

`6ab6f25bd2fe4e6ce2d6f5959ad3e522452cb653`

on temporary branch:

`game-day`

The revision changed `CalendarServiceAdapter.get()` to raise:

`ProviderUnavailableError(provider_involved=False)`

The normal service error translator then produced the contract-compatible `503 provider_unavailable` response.

The deliberately faulty revision did not bypass telemetry.

The failure continued through:

- request middleware;
- Prometheus request/error/latency metrics;
- structured logging;
- tracing;
- release attribution.

Because the failure occurred before the Google call, no Google client span was expected for those requests.

## Detection

The failure was directly detectable through repeated valid Get requests returning:

`503 provider_unavailable`

The telemetry recorded:

- operation `Get`;
- outcome `provider_unavailable`;
- status `503`;
- request/error counters;
- latency;
- request and trace identifiers;
- release identity.

The public Grafana dashboard used during the exercise was:

https://gianthamster2577.grafana.net/public-dashboards/94e9aa89613d4e1faea770e897d47f37

## Triage

The responder investigated the incident using the existing dashboard and:

`docs/reliability/runbook.md`

The responder was not given the implementation-level location of the injected fault.

The responder concluded that the currently deployed revision was causing a user-visible Get reliability failure and selected rollback to a retained known-good immutable artifact.

Responder:

`Yasmin Hassoobh`

Help required from the failure designer:

`NONE`

Runbook issue encountered:

`NONE`

## Mitigation

The responder mitigated the incident by restoring a previously successful immutable Team 2 artifact.

The retained known-good Delivery evidence included:

- Delivery run: `43064300096`
- source SHA: `7854d695cc2b8e84752ec3b4e4aacd2042125478`
- image digest:

`sha256:97e205b2532e5420035c1e57aa489b09d9efe96be1dbefda2452290f7b4f020c`

- smoke: `passed`
- cleanup: `confirmed`

Actual restored source SHA:

`7854d695cc2b8e84752ec3b4e4aacd2042125478`

Actual restored digest:

`sha256:97e205b2532e5420035c1e57aa489b09d9efe96be1dbefda2452290f7b4f020c`

## Recovery

After rollback, Team 2 ran the same canonical real-provider smoke procedure used by the Delivery pipeline.

The smoke workflow exercises the shared provider-backed Calendar behavior and verifies cleanup.

Recovery result:

- known-good revision restored: `YES`
- canonical smoke: `PASS`
- cleanup: `CONFIRMED`
- healthy Get request after rollback: `PASS`
- dashboard recovery visible: `YES`
- availability began recovering: `YES`

Rollback restores deployed application code and configuration.

It cannot undo writes already made to the external Google Calendar provider.

The injected game-day fault itself affected only the read path and made no provider writes.

## What helped

Several existing engineering decisions made the failure bounded and the recovery process predictable:

- the game-day fault affected only one shared operation;
- health endpoints and telemetry remained available;
- application errors continued through the existing public error abstraction;
- telemetry recorded operation, outcome, status, release, and request/trace identity;
- artifacts were identified by immutable image digest;
- the team retained a previously successful known-good artifact;
- the runbook documented rollback rather than requiring an improvised recovery process;
- the same canonical smoke workflow could be reused to verify recovery;
- the smoke workflow included cleanup of test-created data.

## What slowed recovery

`No material recovery blocker was observed during the exercise.`

If applicable, Grafana permission restrictions can also be documented here because they limited alert administration even though the public dashboard remained available for observation.

## Follow-up actions

### Completed follow-up

**Action:** Improve the reliability runbook's known-good artifact and rollback verification instructions.

**Owner:** Team 2 reliability workstream

**Status:** COMPLETED

The runbook now requires the responder to:

1. select a retained successful Delivery artifact;
2. verify its source SHA and immutable digest;
3. confirm that its original run recorded `smoke: passed` and `cleanup: confirmed`;
4. restore that exact immutable artifact;
5. rerun the canonical smoke workflow;
6. confirm cleanup and healthy Get behavior;
7. confirm telemetry recovery.

This follow-up was driven by the recovery exercise and reduces ambiguity around which artifact should be used for rollback.

**Verification:** The documented steps were checked against the existing Delivery implementation and the recovery procedure used during the game day.

## Lessons learned

The exercise demonstrated that the service can fail at the shared-operation level without losing the observability needed to diagnose the incident.

Because the fault passed through the ordinary error and telemetry path, the team could observe a user-visible Get failure while the application, health endpoints, metrics, logs, and traces remained available.

The recovery process also reinforced the value of immutable release identity. The responder did not need to diagnose the exact implementation defect before mitigation; restoring a previously verified immutable artifact and running the same consumer smoke workflow provided a bounded recovery path.

The exercise also confirmed that observability permissions are an operational
dependency. Public dashboard access supports diagnosis, while protected alert
administration and destination access must remain assigned so future responders
can reproduce the end-to-end notification test.

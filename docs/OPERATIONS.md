# Team 2 Calendar operations reference

This page is the short operational index. It links to the canonical deployment,
delivery, observability, and reliability documents rather than duplicating their
procedures.

## Actual resources and ownership

| Resource | Purpose | What breaks without it | Cost/tier | Owner and cleanup |
| --- | --- | --- | --- | --- |
| Render Free web service `ospsd-team-2-calendar` | Runs `app.hosting:app`, validates runtime configuration, and serves the protected Calendar API and health probes | The shared API is unreachable; Google data remains in Google Calendar | Render Free: no compute charge within documented quotas, no disk; cold starts and quota suspension apply | Leon Liu / `LeonLiu0204`; remove the disposable service after submission evidence is secured unless an extension is recorded |
| GHCR immutable image `ghcr.io/airbus-a330/ospsd-team-2@sha256:…` | Preserves the exact tested artifact used for deployment and rollback | A release cannot be reproduced or safely restored by digest | Registry billing was not independently verified; retain only submission/current/known-good evidence digests | Team 2 GitHub organization administrators; retain through submission review, then apply the documented retention decision |
| GitHub Actions Delivery workflow and protected environments | Gates the exact artifact on checks, supplies scoped deployment credentials, deploys, smokes, and records evidence | Releases become manual and undocumented; unreviewed code could receive deployment access if protections are removed | Uses the repository's GitHub Actions allowance; no separate paid runner is configured | Dorien Zhang and Leon Liu, with Team 2 repository administrators; revoke temporary deployment credentials after the exercise/release |
| Grafana Cloud/OTLP telemetry path | Stores and displays bounded metrics, logs, traces, release identity, SLI data, and alerts | Operators lose request correlation, provider timing, golden signals, and alert delivery; API behavior continues because telemetry is fail-open | Existing Grafana Cloud tier; exact ingestion billing is not established in repository evidence | Nicolas Ollivier; retain submission evidence, then follow the account retention policy |

Render's platform-managed Blueprint/resource configuration is the infrastructure
state. The Hobby workspace's direct provider access belongs to Leon; versioned
configuration and routine team deployment are shared through protected GitHub/CD.
Runtime Google
authorization lives only in Render protected configuration. Delivery secrets live
in protected GitHub environments. GHCR publishing uses the job-scoped
`GITHUB_TOKEN`; the Render runtime identity cannot publish images or edit CI, and
the Delivery identity does not receive Google OAuth JSON.

## Operator quick reference

1. **What is running?** One Render Free image-backed web service running
   `app.hosting:app`; see [DEPLOYMENT.md](DEPLOYMENT.md).
2. **Which version?** Read `CALENDAR_RELEASE` in the dashboard/logs and compare
   the Render image digest with the retained Delivery artifact. Do not infer the
   current revision from an old dashboard sample.
3. **Is it healthy?** Check `/healthz` for process liveness and `/readyz` for
   startup readiness. Then use the authenticated, read-only shared Get check;
   readiness intentionally does not depend on Google availability.
4. **Where are logs and traces?** Use the private Grafana dashboard linked from
   [OBSERVABILITY.md](OBSERVABILITY.md); the public dashboard exposes metrics but
   not private log/trace access.
5. **How do I roll back?** Follow [DELIVERY.md#rollback](DELIVERY.md#rollback)
   with a retained immutable digest. Never rebuild or blindly replay writes.

Nicolas independently exercised the integrated application online and used the
deployed telemetry during observability/demo verification. A separate precisely
timed documentation-only operator exercise is not claimed because its timestamp
was not retained.

## Blast radius

- The GHCR publishing job can publish this repository's package but receives no
  Render or Google credential.
- The protected Delivery job can request deployment of an approved digest to its
  configured Render service. A leaked Render key inherits its recorded workspace
  scope, so it must be dedicated, protected, and revoked after use.
- The application directs the runtime Google identity only to its configured test
  calendar. If the OAuth material itself leaked, its worst case is access within
  the granted Calendar scope to every calendar that provider identity can reach;
  it cannot publish images or edit GitHub workflows.
- Production and disposable environments use separate GitHub environment values,
  bearer tokens, Render targets, and test calendars. Untrusted pull requests do
  not receive either environment's secrets.
- One bad merge can make all shared operations on the selected service fail and
  can make writes uncertain. It cannot alter the immutable known-good image;
  rollback restores code/configuration but cannot undo Google Calendar writes.

## Signals and operator actions

| Signal | Question answered | Operator action |
| --- | --- | --- |
| Traffic by operation/release | Are consumers reaching each shared operation and which release handles them? | Check routing/deployment when traffic disappears; use the release filter to bound an incident |
| Latency by operation/outcome | Is consumer-visible response time degrading, and only for failures or also successes? | Compare server and provider spans; investigate provider/cold-start time before changing capacity |
| Errors by operation/category | Is the caller, service, permission, provider response, or provider availability failing? | Follow the category-specific mitigation in the runbook; never retry uncertain writes blindly |
| Worker utilization/capacity | Is the actual AnyIO worker limit saturated? | Reduce load or investigate blocked work; do not add replicas until metric-stream identity is safe |
| Release identity | Did behavior change with a deployment? | Compare failing and known-good digests and use the immutable rollback procedure |
| Get SLI/SLO and budget | Is the representative consumer promise being met over seven days? | When either budget is exhausted, pause discretionary work and prioritize recovery/measurement review |
| `Team2CalendarGetHighFailureRate` | Are enough eligible Get requests failing now to require response? | Open the dashboard and runbook, identify the release/cause, recover, then confirm resolution and smoke cleanup |

The 99% availability and 95% <=1-second latency targets represent an interactive
read consumer while retaining a nonzero error budget. Low traffic is shown with
the numerator and denominator because one failure can exhaust the budget. No data
is unknown, never healthy; check exporter freshness and run the canonical smoke.

## Failure reasoning

| Failure | Expected signal | Mitigation | Recovery limitation |
| --- | --- | --- | --- |
| Google outage | `provider_unavailable`, 503, failed Google child span, availability burn | Confirm provider scope/status; wait or restore only if release-correlated; retry reads only when safe | Rollback cannot restore Google availability |
| Expired/revoked OAuth credential | Provider failure/denial with healthy `/readyz`; sanitized Google operation log | Replace protected runtime authorization and restart through the reviewed path | Code rollback does not restore revoked credentials |
| Quota/rate limit | 503 `provider_unavailable`, quota status/category, provider span failure | Reduce test traffic, respect a meaningful wait, coordinate quota owner | Blindly retrying writes may duplicate events |
| Bad release | Errors begin on one release while health/telemetry may remain available | Deploy retained known-good digest and require the same smoke/cleanup | Existing provider writes and configuration changes remain |
| Telemetry/export failure | Missing/stale series or `telemetry_failure` while API may still respond | Check collector configuration and bounded exporter; use real smoke for service health | Missing telemetry cannot reconstruct lost history and is never proof of health |

Canonical details: [DEPLOYMENT.md](DEPLOYMENT.md), [DELIVERY.md](DELIVERY.md),
[OBSERVABILITY.md](OBSERVABILITY.md), and [RELIABILITY.md](RELIABILITY.md).

# Get failure recovery runbook

**Symptom:** [Get failure alert](alerting.md) fires.

## Fault-image publication preflight

Before starting the bounded fault window, verify the exercise image can be
published without modifying the submission branch:

1. Keep the intentional fault on its temporary branch. Never merge or cherry-pick
   it into `assgn2-ms3-submission` to obtain an image.
2. Build with the repository's pinned Dockerfile/settings and run the canonical
   offline container check before publication.
3. Confirm the publishing identity has package-write permission for the existing
   `ghcr.io/airbus-a330/ospsd-team-2` package. A successful `docker login` does
   not prove the token has the required package scope. If push returns
   `permission_denied`, stop before deployment and obtain reviewed authorization;
   do not switch registries or invent a second deployment path.
4. Resolve the pushed tag to an immutable digest, record its exact source SHA,
   and verify the digest before dispatch. Start the five-minute fault window only
   after the deployment target, known-good rollback digest and responder are ready.

This preflight was added after the prepared game-day image passed the offline
container check but could not be published with the available credential.

## Access and likely causes

Required: private Grafana/Prometheus and sanitized log/trace access, permission for
the approved isolated service/calendar, immutable known-good image and the
existing protected Delivery workflow. API access alone is not Render admin access.

Likely causes to distinguish: faulty application release, expired/revoked Google
authorization, Google rejection/outage, hosted access configuration, or telemetry
export failure. A passing `/readyz` is provider-independent, not real API proof.

## Diagnose, mitigate and verify

1. Confirm service/environment and UTC incident window. Stop injection and contact
   the owner immediately if scope, privacy, cost or recovery safety is uncertain.
2. Open [private dashboard](https://gianthamster2577.grafana.net/d/team2-calendar-shared)
   (or [public metrics](https://gianthamster2577.grafana.net/public-dashboards/94e9aa89613d4e1faea770e897d47f37)).
   Inspect **Get** traffic, categorized failures, latency, saturation and release.
   Use [SLI queries](sli-slo.md) for exact counts/budgets. No series can mean export
   failure; do not interpret it as zero errors. The public page lacks private
   log/trace/admin access.
3. Follow a sanitized request log's trace to HTTP/provider spans. Compare request
   and provider timing, outcome and release. Never enable body/raw-URL/SDK debug
   capture. Check authorization/configuration separately from application health.
4. Restore using [DELIVERY.md#rollback](../DELIVERY.md#rollback): pause merges,
   reconcile running/pending deployments and dispatch **Delivery** from
   `assgn2-ms3-submission` with the retained `image` digest and approved `target`.
   Do not rebuild or guess a cloud command. The [successful delivery artifact](../evidence/reliability-live/README.md)
   provides a known-good candidate; confirm registry retention and target/config
   compatibility first. Preserve service identity and keep its applied Blueprint
   image selection consistent. An ID-less deployment acknowledgement after the
   digest-only fallback needs reconciliation; [reported identity edge](https://github.com/Airbus-A330/OSPSD-Team-2/issues/69#issuecomment-6804954356)
   can otherwise select an old same-digest deployment. Do not guess its outcome.
5. Require the **same** canonical Delivery smoke and cleanup, automatically called
   by `scripts.deploy_render` through `scripts.smoke_calendar.smoke_calendar`.
   It waits up to five minutes for readiness, performs real CRUD/read-back and
   missing-event checks, and never retries writes. Require the artifact to record
   `outcome: successful`, `smoke: passed`, `cleanup: confirmed`. A separate API
   check is useful evidence, not a substitute for this recovery procedure.
6. Confirm the restored image/release, healthy new Get outcomes, improving
   short-window results and stopped budget burn. Check actual resolved receipt.
   Seven-day incident failures remain in the window; recovery need not make the
   rolling SLI instantly 100%. Silence or an old healthy instance is not proof.
7. Remove the fault, restore temporary settings, stop test traffic and perform
   standard smoke cleanup. Have the owner confirm disposable resource/cost
   cleanup. Never destroy shared resources; escalate persistent failures.

## What recovery cannot undo

Image rollback does not undo Google Calendar writes, OAuth revocation/rotation
or environment changes. Render Free has no persistent disk: startup reconstructs
the disposable token cache from protected runtime configuration. Do not restore
stale credentials or depend on the token file surviving. Handle ambiguous writes
with the calendar owner; delete only test-owned data and never replay them blindly.

The [exercise plan](../RELIABILITY.md#game-day) sets the bounded
failure and abort conditions. An unrelated responder must use this runbook without
coaching from its failure designer; record any safety intervention honestly.

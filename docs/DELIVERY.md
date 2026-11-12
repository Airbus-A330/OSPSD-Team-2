# Delivery and rollback

Status: implemented and exercised. Retained evidence records an immutable
deployment with real-provider smoke/cleanup and a bounded faulty-release recovery
using the same Delivery path. Public contract unchanged; no dependency changes.
Use the existing [Dockerfile](../Dockerfile), [Blueprint](../infra/render.template.yaml),
and [deployment setup](DEPLOYMENT.md).

Leon Liu owns the direct Render account. Leon and Dorien Zhang integrated the
protected GitHub Actions/CD path so routine team deployments do not require
sharing Leon's provider credentials.

## One-time external setup

Leon Liu is the Render account owner. Platform state is protected by Render;
versioned configuration, artifact identity, and routine deployment changes are
shared through the protected GitHub/CD path described in
[DEPLOYMENT.md](DEPLOYMENT.md). The existing image-backed service is provisioned
from that Blueprint. Its image repository must be
`ghcr.io/airbus-a330/ospsd-team-2`: Render requires deploy requests to match the
configured repository. Keep Blueprint Auto Sync **off**. Delivery deploys a
digest to that same service through the Render API; it does not create resources
or change runtime configuration. Before any later Blueprint sync, regenerate
the applied Blueprint with the latest successful digest to avoid reinstating an
obsolete image. Retain each generated Blueprint as the image-selection record.

Repository administrators must establish these protections before delivery:

1. Protect `assgn2-ms3-submission`: require a teammate approval, current Build,
   Format, Tests and Infrastructure checks, and an up-to-date branch. Restrict
   direct pushes and bypasses. YAML alone cannot require reviewed merges.
2. Create GitHub environments `production` and `disposable`, restricted to the
   deployment branch. Set required reviewers according to team policy. Reviewer
   gates may pause delivery but require no developer deployment commands.
3. In each environment set variables `RENDER_SERVICE_ID`, `CALENDAR_BASE_URL`
   (HTTPS origin) and secrets `RENDER_API_KEY`, `CALENDAR_API_TOKEN`. Verify the
   URL belongs to that service. Disposable settings must target a separately
   authorized disposable instance of the **same Blueprint**, with its own test
   calendar. Never point disposable settings at production.
4. Store Google OAuth JSON and calendar ID only in Render runtime configuration
   as documented in [DEPLOYMENT.md](DEPLOYMENT.md). GitHub receives the hosted
   HTTP bearer token, not the
   OAuth JSON. Use Calendar events scope and a Google identity limited to the
   designated test calendars.
5. Use a dedicated Render automation identity limited to Team 2's deployment
   workspace/resources. Render keys inherit owner access; they are **not**
   service-scoped. Do not use a personal key with unrelated workspaces. Record
   actual owner/scope, resolve unavailable finer permissions with Leon,
   and revoke/rotate after the exercise. Code only reads service/deployment data
   and creates deployments;
   it needs no resource deletion or runtime configuration updates.
6. GHCR publishing uses short-lived `GITHUB_TOKEN` with `packages: write` only
   in the artifact job. Other jobs receive only `contents: read`. Associate the
   package with this repository and allow Actions publishing. An owner must
   make the first secret-free package public, or separately configure a
   read-only registry pull credential in Render before first deployment.
7. Retain current, previous known-good and exercise digests and their SHA tags
   through submission review; exclude them from registry garbage collection.

PR jobs have no deployment environments/secrets and use `pull_request`, never
`pull_request_target`. Delivery triggers only on deployment-branch pushes or
authorized dispatch on that branch; other refs skip all jobs. Store credentials
as environment secrets, never repository-wide secrets. Branch/environment
protections also prevent unreviewed workflow changes from obtaining them.

## Normal release and failure behavior

[Delivery](../.github/workflows/delivery.yml) calls the same Build, Format,
Tests and Infrastructure workflows on the exact merged SHA. All must pass
before building. Tests explicitly runs the tagged shared conformance suite
through controlled Python and HTTP implementations. Infrastructure schema
validation runs on every PR, including all infrastructure changes, avoiding
pending required checks from path filters. This does not apply IaC or replace
Render's workspace-aware bootstrap validation/change preview.

The artifact job builds the existing linux/amd64 image **once**, tagged with
the source SHA, then runs `make container-check` against it. It pushes that same
image and resolves its registry digest. Deploy receives the digest; Render
pulls it without rebuilding. Runtime secrets/config stay outside the image.
A rerun can yield a different digest for the same SHA; retained **digests** are
authoritative for rollback. Never rebuild a known-good release to restore it.

The script sends `imageUrl` to Render's [create-deploy API](https://api-docs.render.com/reference/create-deploy).
It accepts `201 Created` and `202 Queued`. Requests first use a unique
`delivery-<UUID>` tag on the digest-qualified reference, for example
`registry/repository:delivery-<UUID>@sha256:<digest>`. The digest still selects
the same published bytes; this does not build/publish a second image or require
creating that tag in the registry. If Render rejects that combined reference
shape (for example with `400`/`422`), the script retries once with the canonical
digest-only reference.

When the response includes an ID, the script monitors it directly. An empty or
ID-less `202` instead triggers bounded discovery through Render's paginated
[deployment list](https://api-docs.render.com/reference/list-deploys), matching
only the exact request-specific `image.ref`. Discovery and ID polling share the
same 15-minute deadline. The script never resubmits the POST, selects the latest
deployment, or treats an older/concurrent deployment of the same digest as its
own. It checks every page before selecting a unique match. Multiple matching
IDs fail as ambiguous; a missing match waits until the deadline.

Render must preserve the full submitted image reference in `image.ref` for
ID-less discovery. Missing/normalized metadata is not sufficient proof of
identity. If discovery fails or the acknowledgment is lost, inspect Render
before retrying: the accepted request can still proceed independently. Evidence
retains `request_image`, `deployment_tracking` when known, any ambiguous
`candidate_deploy_ids`, and `reconciliation_required: true`. Use that exact
reference to locate and reconcile the queued deployment; do not deploy another
revision while its outcome is unresolved. This flag is cleared only after the
identified deployment's smoke and cleanup pass. Live verification must confirm
Render accepts and preserves the digest-qualified correlation reference.

Render `live` only proves platform health. The GitHub deployment job remains unsuccessful until
real smoke and cleanup pass. A Render `live` deployment can therefore have a
**failed** Delivery result. There is no automatic rollback or traffic isolation.

Smoke waits up to five minutes for `/readyz` to handle Free-plan cold starts,
then checks POST → GET → PUT → GET → DELETE → missing GET and repeated DELETE,
including shared fields, stored instants, statuses and missing-event errors.
It uses the hosted API and real Google provider with no dependency overrides.
Before deploying, the script verifies that the smoke origin matches Render's
canonical service URL, preventing a healthy different service from certifying
the candidate. Use that canonical URL rather than a custom-domain alias.
It always attempts cleanup for a returned ID, even when other create response
fields are malformed, and confirms missing GET. Writes are never retried.
A lost/malformed create response without an ID has an unknown outcome: the
calendar owner must find the uniquely named `OSPSD delivery smoke ...` event
on the test calendar and delete it. Unknown/failed cleanup cannot mean success.

Release and rollback share `calendar-delivery` concurrency with cancellation
disabled for running jobs. GitHub keeps one running and one pending run; a
newer pending run can replace an older one. This is not FIFO. Pause merges and
clear pending releases before rollback so a later run cannot supersede recovery.
Avoid Render manual deployment, Blueprint sync or another automation while a
delivery runs. Emergency cancellation can leave Calendar data or a running
Render deployment; reconcile both before resuming.

## Rollback

1. Pause merges. Wait for the running Delivery and cancel obsolete pending runs.
2. Download the last successful `delivery-<run>-<attempt>` artifact. Require
   `outcome: successful`, `smoke: passed`, `cleanup: confirmed`. Record its exact
   `image` digest and the source SHA from that successful run. Latest Render
   `live` alone is not proof of a known-good release.
3. Confirm the digest remains in GHCR. Check runtime configuration compatibility;
   image rollback does not restore env values. If changed, restore reviewed
   configuration separately in protected Render settings without exporting it.
4. Actions → Delivery → Run workflow: select `assgn2-ms3-submission`, paste
   the retained digest reference, select `production` (or `disposable` for the
   exercise) and approve the environment if required. Dispatch never rebuilds.
   Use the integrated workflow revision. GitHub must know the workflow on the
   default branch for the Run workflow UI; arrange reviewed workflow registration
   with the repository administrator.
5. Require the **same smoke and cleanup**. Retain the rollback evidence with
   the original successful and failed runs. Update the applied Blueprint image
   record before later IaC sync. Resume merges after verifying the restored digest.

**Code/config rollback does not undo writes already made to Google Calendar.**
Inspect ambiguous writes and clean up only test-owned events. Never replay a
failed create blindly. Revoked/expired OAuth needs reauthorization, not an image
rollback. Manual production dispatch must select a proven known-good digest;
it can otherwise promote an unverified digest, so protected reviewers must
check the prior successful evidence.

## Authorized disposable faulty-release exercise

This is a procedure, **not execution evidence**. Obtain explicit authorization
to publish, deploy and inject a bounded failure first. Use only the confirmed
disposable service/calendar. Do not weaken normal required checks.

1. Dispatch a known-good retained digest to `disposable`. Require smoke and
   cleanup success and download its artifact.
2. In a temporary directory prepare a two-line faulty Dockerfile:
   `FROM <known-good-digest-reference>` and
   `CMD ["python", "-c", "raise SystemExit('intentional disposable startup failure')"]`.
   It inherits the same app/UID. Build once for linux/amd64, push with a unique
   exercise tag to the **same** GHCR repository, and retain the actual registry
   digest and Dockerfile. This explicitly authorized exercise artifact should
   fail the normal container check; it is not a normal merge release.
3. Dispatch its digest to `disposable`. Expect Render's health gate to fail
   (Render may keep the old instance serving). Confirm a failed Delivery for
   the requested deploy ID; never accept a smoke against the old instance as
   candidate success. Retain failure evidence. If polling times out first,
   inspect Render and wait/cancel that exact deployment before recovery so it
   cannot overwrite the restored revision later.
4. Dispatch the original known-good digest back to `disposable`. Require the
   same smoke and confirmed cleanup. Record restoration of the exact digest,
   resource identities and absence of remaining smoke data.
5. Retain all three run artifacts before their 90-day expiry. Coordinate
   disposable teardown with #68 after submission evidence is secured.

## Evidence

Use [the evidence checklist](evidence/delivery/README.md). Every attempted deploy
uploads sanitized `delivery.json` and generated `delivery.yaml` on success or
failure for 90 days. JSON identifies image digest, workflow SHA/run, returned
Render deploy ID, request-specific image reference, tracking/reconciliation
state, platform status, smoke, cleanup and final outcome. On rollback
`workflow_sha` identifies the tooling revision; use the original successful run
to identify the image's source SHA. Reports omit secrets, event IDs and payloads.
Retain actual successful/failed/restored run URLs and downloaded artifacts for
submission, plus owner/reviewer coordination and cleanup confirmation. Controlled
tests do not establish live deployment or rollback evidence.

Failure diagnostics include a fixed stage, numeric HTTP status when a response
was received, and a fixed error category in both the CLI error and JSON evidence.
A fallback request also preserves `initial_deploy_http_status`. A transport
failure reports no HTTP status for that stage, rather than reusing a prior
successful response. Response bodies, headers and exception messages are never
included. These fields diagnose future runs; they cannot recover details omitted
from older evidence.

# Container and infrastructure — Issue #68

Delivery, protected CI configuration, smoke checks, and rollback are implemented;
see [DELIVERY.md](DELIVERY.md). The retained Delivery and game-day records provide
live deployment, real-provider smoke/cleanup, and recovery evidence. Leon Liu
deployed and tested the service on Render; Nicolas Ollivier independently tested
the integrated application locally and against the hosted build.

Status: local implementation and cloud implementation on Render. Do not interpret a passing local
check as completion of the required teammate deployment exercise.

## Selected approach and ownership

Use one Render **Free** image-backed web service, one worker, and a
version-controlled Blueprint generated from `infra/render.template.yaml`.
There is no persistent disk or database. This follows Alexander's November 9
clarification that ephemeral storage is sufficient for this deployment.
The Dockerfile installs production dependencies from `uv.lock`, including the
shared package's locked revision. Python and uv base images are digest-pinned.
Render receives a prebuilt **linux/amd64** image by digest, not `latest`.
This is a repeatable locked-dependency build, not a claim of bit-identical image
bytes: the build-only Git install and upstream build tooling can change.
Retain and redeploy the exact published image digest instead of rebuilding it.

Google remains the event store. `/var/data/token.json` is a disposable local
credential cache, not durable infrastructure state. Render's protected runtime
configuration holds the authorization needed to reconstruct that cache.
One worker serializes credential refresh between request threads. Keep that
boundary until concurrency and credential handling are deliberately revisited.

| Responsibility / prerequisite | Current status |
| --- | --- |
| Infrastructure implementation and direct Render owner | Leon Liu (`LeonLiu0204`; Xingjian Liu) |
| Independent hosted application/telemetry verification | Nicolas Ollivier |
| Cost policy | Free compute, no disk; no paid upgrades or additional charges authorized |
| Workspace access | Render Hobby direct account access belongs to Leon; routine team changes use protected repository/CD controls |
| Delivery pipeline and registry publishing | Dorien Zhang and Leon Liu; use this Dockerfile and Blueprint |
| Deployment branch / approved image digest | `assgn2-ms3-submission`; Delivery records the exact published digest |
| Teardown expectation | Account owner removes the disposable environment after submission evidence is secured, unless an extension is agreed and recorded |

### State, secrets, and access boundary

- Render's platform-managed Blueprint and resource configuration is the applied
  infrastructure state. The generated digest-specific Blueprint is the reviewed
  image-selection record. There is no Terraform/OpenTofu state file in this
  repository.
- Leon Liu owns and controls the direct Render account. The Hobby workspace is
  intentionally single-owner at the provider-account layer. Routine team changes
  use the protected GitHub Delivery workflow, so teammates do not share Leon's
  Render credentials and no infrastructure state depends on a local machine.
- Google OAuth JSON and the Calendar ID live only in Render protected runtime
  configuration. They are read by the runtime identity and are not supplied to
  the image build or GitHub Delivery job.
- Render deployment credentials and the hosted HTTP bearer token live in protected
  GitHub environments. Repository/Actions administrators and configured environment
  reviewers control access; pull-request jobs receive no deployment environment.
- GHCR publishing uses only the artifact job's short-lived `GITHUB_TOKEN`. Runtime,
  publishing, and deployment identities are separate. Sanitized Delivery artifacts
  contain identifiers/status only, never secret values or response bodies.

The [Free plan](https://render.com/docs/free) has no compute charge within its
quotas and no disk charge because none is provisioned. It has 750 instance hours
per workspace/month and separate bandwidth/build quotas. With no payment method,
exhausted applicable quotas suspend services/builds rather than enabling paid
usage; confirm account billing settings before deployment. Registry costs are
separate. Do not select paid services or upgrade the workspace implicitly.

Free instances sleep after 15 minutes without inbound traffic; wake-up takes
about a minute. Local file changes are lost on restart, redeploy or sleep.
The platform can restart a Free instance at any time. This is a classroom/demo
tradeoff, not an always-on availability guarantee. Coordinate cold-start timeout
handling with #69 and the SLO owner. Only safe readiness/GET probes should be
retried; do not blindly resend uncertain writes to wake a sleeping service.

[Hobby workspaces cannot invite teammates](https://render.com/docs/team-members).
The team therefore uses a deliberate split: Leon retains direct provider-account
control, while versioned configuration, artifact identity, deployment history,
review, and routine deployment changes are shared through GitHub and GHCR. Do not
share account passwords or assume a paid workspace is approved.

## Local checks

From the repository root, with Docker running, Python 3.12, and uv >= 0.12.17:

```sh
uv sync --locked
make check
make infra-check
make container-build
make container-check
```

`infra-check` materializes the template with a **synthetic** digest solely for
schema validation against Render's official schema. It does not prove an image
exists or that the workspace will accept the plan. The temporary file is removed.
`container-check` runs the actual image as UID 10001 with external networking
disabled and synthetic credentials. It checks failed startup without config,
private token seeding, protected traffic, and healthy readiness during a
controlled provider failure. No Google data is read or changed.

`.dockerignore` allowlists application Python sources and dependency/build files.
The final image contains no repository history, host virtualenv, runtime secrets,
or development test dependencies. Neither Docker build arguments nor image labels
should ever contain credentials. No source dependency or `uv.lock` update is
required for this issue.

## Runtime configuration

Containers run `app.hosting:app`; local development continues to use
`app.main:app`. Both use the same Calendar routes and provider implementation.
The hosted wrapper adds startup validation and a deployment access boundary.
It composes the base factory's lifespan instead of replacing its startup/shutdown
work, and forwards any yielded lifespan state. Readiness is enabled only after
base startup completes, and disabled before shutdown. Base request middleware
remains outside hosted access checks so it can observe early 403 responses.
The #73 telemetry implementation can therefore initialize, export and clean up
through the actual container entry point.

| Variable | Value / handling |
| --- | --- |
| `PORT` | Render listener port; Blueprint sets `10000` |
| `GOOGLE_CALENDAR_ID` | Explicit dedicated test calendar ID, supplied in protected runtime configuration |
| `GOOGLE_CALENDAR_TOKEN_JSON` | Full authorized-user token JSON from an initial local OAuth authorization; secret, supplied only at runtime |
| `GOOGLE_CALENDAR_TOKEN_FILE` | `/var/data/token.json`, a private ephemeral cache; no disk mount |
| `GOOGLE_CALENDAR_NONINTERACTIVE` | `1`; set by the container and hosted startup |
| `CALENDAR_API_TOKEN` | Random, at least 32 ASCII characters without whitespace; share securely with authorized testers and the #69 smoke-check secret store |

Complete the initial browser authorization locally using [PROVIDER.md](PROVIDER.md)
with the dedicated Google test calendar, the Calendar events scope, and an account
allowed to access that calendar. Supply the resulting authorized-user JSON
(including `client_id`, `client_secret`, and `refresh_token`) through Render's
protected environment inputs. Do not paste it into GitHub, chat, commands, or logs.
The hosted service does not need the separate desktop OAuth client JSON file:
the authorized-user JSON already contains the refresh-client information.

At every startup, validate `GOOGLE_CALENDAR_TOKEN_JSON` and atomically initialize
`/var/data/token.json` with mode 0600, replacing any old local cache. The Docker
image creates `/var/data` owned by UID/GID 10001; no mounted volume, shell access
or manual ownership bootstrap is required. Startup never contacts Google.
Missing or malformed runtime authorization fails clearly even if a stale cache
exists. During service use, refresh is serialized and written atomically to this
private cache; it never opens a browser or updates Render's stored secret.

After local storage is lost, the next start reconstructs the cache from the
runtime configuration and refreshes an expired access token on provider use.
This requires a still-valid refresh token in that configuration. OAuth tokens
can expire or be revoked; an external Google OAuth app in Testing generally has
[a seven-day refresh-token lifetime](https://developers.google.com/identity/protocols/oauth2#expiration)
for Calendar scopes. Confirm authorization before the demo. Durable storage would
not prevent that expiry either.

For reauthorization or refresh-token rotation, update the protected runtime JSON
and redeploy/restart; the new seed replaces the old cache. Do not rely on edits
inside the running container surviving a restart. Never print credentials or put
them in Git, the image, Blueprint YAML, or deploy-hook URLs.

`GET /healthz` reports the running process. `GET /readyz` returns 200 only after
local startup validation, otherwise 503. Neither calls Google. Use `/readyz` as
the platform health path. A passing probe does not establish valid Google access;
the #69 real-provider smoke check does that.

All other hosted HTTP paths, including docs, require
`Authorization: Bearer <CALENDAR_API_TOKEN>`. Failed access returns a sanitized
403 JSON response before provider work. This deployment boundary does not change
the shared Python contract. Health responses expose no credentials or calendar
IDs. Uvicorn access logs are disabled to avoid logging raw event paths; existing
sanitized application logs remain. Issue #70 can add structured telemetry here.

## Prepare the artifact and preview infrastructure

1. Obtain the approved source revision that includes completed MS2 work and #68.
   A teammate must clone it into a fresh directory and run the local checks above.
2. The #69 owner builds and publishes this image once and records its registry
   digest. Publishing is a separate authorized action. Do not invent a digest or
   treat the local Docker image ID as a published registry digest. Use a public
   project image containing no secrets, or configure a least-privilege registry
   pull credential in Render before selecting a private image.
3. Generate the deployment file from that exact published reference:

   ```sh
   python3 scripts/render_blueprint.py --image "$CALENDAR_IMAGE_REF" > infra/render.yaml
   ```

   `CALENDAR_IMAGE_REF` must be `registry/path@sha256:<64 hex digits>`.
   Review and version-control the generated `infra/render.yaml` through the
   team's normal approval flow; it contains infrastructure and the artifact
   reference, never secret values. Regeneration with the same input is identical.
4. Run `render blueprints validate infra/render.yaml` with Render CLI >=2.7.0
   and the intended workspace access. This is the platform-aware check in addition
   to `make infra-check`; it is not an apply or deploy command.
5. Review the Git diff against the last applied file. Check resource name,
   image digest, region, instance count, `plan: free`, absence of disks, and runtime variables.
   Use Render's new-Blueprint change preview on initial creation. For updates,
   review the current workspace resource configuration as well as the versioned
   diff before Manual Sync. Schema validation alone is **not** a cloud-state plan.
   Record the proposed changes before applying; stop if resource replacement or
   additional cost is unexpected.

## Provision, shared state and repeat application

After account owner, the access/state arrangement and deployment authorization are confirmed:

1. In the agreed workspace, create **one** Blueprint linked to the
   approved repository branch, with path `infra/render.yaml`. Review Render's
   proposed resources before deploying. Supply the three `sync: false` inputs
   from the runtime configuration table through Render's protected UI.
2. Disable Blueprint **Auto Sync** manually in its Settings. Render's
   [Blueprint reference](https://render.com/docs/blueprint-spec#autodeploytrigger)
   states that `autoDeployTrigger` has no effect for prebuilt-image services, so
   the template omits it. Keep Blueprint Auto Sync off because the reviewed
   GitHub Delivery workflow owns deployments.
3. Verify the service is owned by that Blueprint, and record its ID,
   Blueprint link, applied source commit, image digest and authorized operators.
   These mappings and current configuration are the platform-managed IaC state.
   Direct Render access remains with Leon Liu. Routine team deployment changes
   use protected GitHub/CD configuration, immutable GHCR artifacts, and retained
   workflow history; no shared local credential or local-only state is required.
4. Verify `/readyz`, unauthenticated access rejection, and an authenticated GET
   through the deployed shared Calendar API against the dedicated Google calendar.
   Allow for cold start before expecting JSON API responses.
   Follow [HW2_MS2_GET_VERIFICATION.md](HW2_MS2_GET_VERIFICATION.md) for the
   successful/missing-event checks, adding the deployment authorization header.
   Record statuses and release identity, not response payloads or private IDs.
5. Use **Manual Sync on the same Blueprint** with the unchanged file/image.
   Do not create another Blueprint. Confirm the service ID remains
   unchanged, no duplicate resources or unexpected replacement occurs, and the
   API still works. Record the actual diff/no-change evidence; this has not been
   verified by the local tests.

Do not manage these resources from a second Blueprint. Changes made manually to
Blueprint-managed fields can be overwritten at the next sync. Secret values with
`sync: false` are supplied at initial creation; add/rotate later secrets in the
protected service configuration. Do not put secrets into generated YAML to
force them to synchronize.

## Teardown

The independent tester must perform this after the disposable-environment test:

1. Coordinate with #69 to stop deployment triggers and disable Blueprint Auto
   Sync. Retain only redacted verification evidence and required image references.
2. Remove the service definition from the applied Blueprint and sync that change
   so the resource is unmanaged. Removing YAML alone does **not** destroy it.
3. In the workspace, explicitly delete the now-unmanaged test service. Confirm
   it is absent; this free configuration has no disk or database to delete.
   Merely deleting a managed service can cause a later sync to recreate it.
4. Remove the unused Blueprint, protected runtime values, registry pull/deploy
   credentials and temporary tester access if no longer needed. Revoke the
   dedicated Google authorization and delete only test-owned Calendar data.
5. Clean up disposable published images according to #69's retention policy.
   Record completion time, operator and resource inventory; never save tokens,
   raw plans containing secrets or unredacted environment exports as evidence.

Cloud deletion is not performed by any local Makefile target.

## Operational handoff and remaining verification

The Delivery workflow builds `Dockerfile` once for linux/amd64, publishes and
retains the digest, renders the same Blueprint, injects runtime values separately,
then smoke-tests with the deployment bearer token. Keep exactly one instance/worker. Image rollback
does not undo Google Calendar writes or rotate the protected runtime secret.
Each new start restores the token cache from the current runtime configuration.
Allow a bounded cold-start wait for readiness before testing the API. Do not
allow a later Blueprint sync to accidentally reinstate an obsolete image digest.
The deployment pipeline, rollback exercise, telemetry, and SLO evidence are
documented in [DELIVERY.md](DELIVERY.md), [OBSERVABILITY.md](OBSERVABILITY.md),
and [RELIABILITY.md](RELIABILITY.md).

The retained evidence establishes local infrastructure validation, Render
deployment, independent hosted application testing, protected automated delivery,
live API reachability, and recovery. It does not retain a distinct transcript of
an independent teammate provisioning from a fresh checkout, an unchanged second
Render sync, or a completed teardown; do not invent those narrower events.

References: [Blueprint management](https://render.com/docs/infrastructure-as-code),
[Blueprint fields/validation](https://render.com/docs/blueprint-spec),
[prebuilt images](https://render.com/docs/deploying-an-image),
[free instance limits](https://render.com/docs/free), and
[runtime secrets](https://render.com/docs/configure-environment-variables).

## Original paid-disk implementation verification — 2026-11-09

Historical record for the implementation later committed as `fcc8858`. It does
not verify the subsequent free-plan changes; see the new verification record below.

Reviewed branch revision: [`fcc8858`](https://github.com/Airbus-A330/OSPSD-Team-2/commit/fcc8858d30f85cc99f3b9379b975d3dbc8e65b37),
committed and pushed in PR #75, based on `7116084`. The following local results
were recorded on macOS for that implementation; they do not establish Windows
compatibility. This is not a published image release or a deployed revision.
The local image tag is
`ospsd-team2-issue68:local`; its final runtime image config ID was
`sha256:c9d1b4e76cff74311781f88adbb37ced030bb67578d5dff935c389fe9e0d7cd2`.
Do not use that local config ID as a registry pull digest.

Commands actually run:

- `uv tool run --from uv==0.12.17 uv run --locked make check`: PASS — Ruff format,
  Ruff lint, mypy (39 files), 632 tests, compilation and application import.
  Includes the existing controlled shared GET conformance cases. It does not
  claim completion of #67's full shared-operation migration/conformance work.
- `.venv/bin/python -m pytest tests/test_hosting.py tests/test_google_calendar.py -q`:
  PASS — 32 focused tests after the final credential refresh change.
- `make infra-check`: PASS — official Blueprint JSON Schema, synthetic image
  reference; not workspace-aware validation or an infrastructure apply.
- `make container-build container-check`: PASS — actual linux/amd64 image,
  UID 10001, fail-fast startup, runtime token seeding, access protection and
  healthy probes during a controlled provider outage, with external networking
  disabled. The test container was automatically removed.
- `git diff --check`: PASS. Reviewed changed sources and build context rules for
  secrets; only explicitly synthetic fixtures were introduced.

One existing Starlette/AnyIO deprecation warning remains. An initial mypy module
naming error and an incorrect schema URL were corrected before these final runs.
No actual credentials, provider requests, cloud provisioning or registry push
were used in these local checks. The implementation was subsequently committed
and pushed as `fcc8858`.

GitHub CI for `fcc8858`: all six Build, Format and Tests checks (push and pull
request) passed. PR runs: [Build](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/42749202853),
[Format](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/42749203141),
and [Tests](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/42749202844).
These results apply to that commit, not subsequent unpushed review fixes.

### Review-fix verification — 2026-11-09

Local review fixes on top of `fcc8858` passed `make check` (632 tests),
`uv run --locked mypy --platform win32 .` (39 files), `make infra-check`,
and `make container-build container-check`. The Linux container check explicitly
verifies UID 10001 and token mode 0600. The Windows-targeted mypy check ran on
macOS; native Windows pytest still needs teammate confirmation. These fixes were
committed and pushed as `f48a62b`. Its observed GitHub checks passed:
[Build](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/42758331868),
[Format](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/42758332332),
and [Tests](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/42758331899).
These CI results do not cover the following local free-plan changes.

## Free-plan verification — 2026-11-09

Historical local verification for the free-plan update based on `f48a62b`,
subsequently committed and pushed as `f7d60dc`. No cloud resources or real Google
requests were used for that verification.

- `make check`: PASS — formatting, lint, mypy (39 files), **636 tests**,
  compilation and application import. The existing Starlette/AnyIO warning remains.
- `uv run --locked mypy --platform win32 .`: PASS — 39 files. This is a
  Windows-targeted static check on macOS, not a native Windows test run.
- Restart coverage: PASS — cache discarded or retained, runtime-secret rotation,
  missing-secret rejection despite an existing cache, and controlled token refresh.
  Startup never contacts Google; non-Windows permission assertions remain enabled.
- `make infra-check`: PASS — official schema with `plan: free` and no disk;
  this is not a platform preview or provisioning result.
- `make container-build container-check`: PASS — linux/amd64, no mounted volume
  and no external network; UID 10001 recreates `/var/data/token.json` with mode
  0600 after deletion. Missing configuration, protected API access and readiness
  during a controlled provider outage were also checked.
- `git diff --check`: PASS. The dependency lockfile is unchanged.

The local runtime image config ID is
`sha256:e2f0f3901fd281c267687f1b335b69fee3aa7552e94854b8d1e1e3b7feaf46db`.
It is not a published registry digest.

Real cold-start recovery with Google, cloud reapplication and independent teammate
acceptance still need deployment evidence. Local tests do not resolve Hobby's
shared-state/access limitation.

## Hosted integration review verification — 2026-11-10

Source: local fixes on `f7d60dc`. An earlier verification temporarily included
`assgn2-ms3-submission@9e663a9`. That local merge was subsequently aborted at
the author's request; DESIGN conflict resolution is deferred. The current
working tree retains only the hosted integration repairs and their tests/docs.
The combined-baseline results below are historical verification evidence, not
the current branch's test count.

After aborting that merge, the retained repairs were revalidated on `f7d60dc`:
`make check` passed with **640 tests**; Windows-targeted mypy passed for 39 files;
`make container-build container-check` passed. No baseline synchronization or
DESIGN conflict resolution is included in the current working tree.

- Before the fix: all four new hosted-factory regressions failed.
- In the temporary combined baseline: `make check` passed (format, lint, mypy, **750 passed / 1 skipped**,
  compilation and import). The existing live Google workflow is opt-in and was
  skipped; no actual provider verification is claimed.
- `uv run --locked mypy --platform win32 .`: passed, 42 files. This is still a
  static Windows-target check, not native Windows pytest.
- `make infra-check container-build container-check`: passed. The container
  smoke test now uses the module-level `app.hosting:app` entry point.
- In a separate temporary source snapshot, combined these changes with #73's
  `app/main.py`, `app/telemetry/` and locked dependencies at `822457f`.
  Ten selected hosted/lifecycle/access tests passed.
- Built that snapshot as `ospsd-team2-issue68-telemetry:verify`. Inside a
  linux/amd64 container with `--network none`, ran `app.hosting:app` under
  Uvicorn against a loopback-only OTLP receiver and a controlled Calendar service.
  Confirmed actual telemetry startup and shutdown, HTTP 200 and early 403
  correlated logs/traces, request metrics for success/access_denied, no service
  call on denial, and no credentials/event contents in the exported signals.

The temporary snapshot is a focused hosted/HTTP telemetry integration check.
It does not merge #73's provider instrumentation or unrelated changes into this
branch, and does not prove the full #73 merge or deployed OTLP connectivity.
The production lockfile and telemetry implementation are unchanged by this fix.
Nicolas/Max should recheck the final integrated revision before deployment.
No cloud resources, notifications, commits or pushes were made for this update.

### Issue #68 acceptance criteria, in issue order

PASS below refers only to the stated local evidence. Cloud results are not inferred.

| # | Criterion | Status | Evidence or remaining step |
| --- | --- | --- | --- |
| 1 | Reproducible deployable artifact | PASS | Pinned bases, locked install, successful linux/amd64 build and runtime check |
| 2 | Locked application dependencies | PASS | `uv sync --locked --no-dev --no-editable`; lockfile unchanged |
| 3 | No credentials/environment secrets in artifact | PASS | Allowlisted build context, explicit copies, no secret build inputs |
| 4 | Version-controlled IaC | PASS | Free-plan template and deterministic digest-specific rendering are committed; retained Delivery evidence records an applied immutable image |
| 5 | Hosting/IaC tools and rationale documented | PASS | Selected approach above |
| 6 | Preview before apply | IMPLEMENTED; TRANSCRIPT NOT RETAINED | Deterministic Blueprint generation, schema validation, and review procedure are implemented; a distinct platform-preview transcript is not retained |
| 7 | Unchanged reapply avoids duplicates/replacement | IMPLEMENTED; TRANSCRIPT NOT RETAINED | Stable resource name/digest rendering and repeat-generation tests prevent duplicate definitions; an actual unchanged second-sync transcript is not retained |
| 8 | Protected/shared infrastructure state | PASS | Render protects platform state under Leon's account; versioned configuration, deployment history, immutable artifacts, and routine team changes are shared through protected GitHub/CD |
| 9 | Protected runtime Google credentials | PASS BUT EXTERNAL AUDIT LIMITED | Runtime-only authorization and disposable cache are implemented; successful real-provider smoke establishes working runtime configuration without exposing its value |
| 10 | Validate config during startup | PASS | Hosted lifecycle and failure tests |
| 11 | Clear sanitized missing-config failure | PASS | Unit and actual-container checks |
| 12 | Health/readiness endpoint | PASS | `/healthz`, `/readyz` in hosted entry point |
| 13 | Temporary Google outage avoids restart loop | PASS | Provider-independent async probes; controlled 503 leaves readiness healthy |
| 14 | Manual prerequisites documented | PASS | Accounts, authorization, permissions, image publishing, runtime secrets and free-plan limits |
| 15 | Expected cost/free-tier assumptions | PASS | Free compute quotas, no disk, separate registry costs and no paid upgrades documented |
| 16 | Actual account owner documented | PASS | Leon Liu / `LeonLiu0204` |
| 17 | Teardown date/cleanup expectation | PASS | Remove after submission evidence is secured unless an extension is agreed and recorded |
| 18 | Complete teardown instructions | PASS | Unmanage, delete service, remove secrets/access and verify inventory |
| 19 | Independent teammate provisions fresh checkout | EVIDENCE LIMIT | Nicolas independently tested locally and against the hosted build; a distinct non-author provisioning transcript is not retained |
| 20 | Teammate reaches deployed shared API | PASS | Independent 11-check API run reached the deployed service and confirmed cleanup; see `evidence/reliability-live/README.md` |
| 21 | Second actual IaC apply has no unexpected change | EVIDENCE LIMIT | Repeat-generation is tested; a separate cloud reapply transcript is not retained |
| 22 | Teammate tears down from documentation | DOCUMENTED | Complete teardown procedure exists; no completed teardown event is claimed before submission evidence is secured |
| 23 | No secrets in source/build/logs/plans/CI artifacts | PASS | Runtime/environment separation, allowlisted image, sanitized Delivery artifacts, telemetry privacy inspection, and repository secret/state scans |
| 24 | Required CI checks pass | PASS FOR RETAINED DELIVERY REVISION | Delivery run `43064300096` succeeded for source `7854d695cc2b8e84752ec3b4e4aacd2042125478`; final merge-commit CI remains a release step |

## Deployment verification record

Leon tested the infrastructure/application locally, deployed it through Render,
and tested the Render cloud build. Nicolas independently tested the integrated
application locally and online against that hosted build while verifying the
observability integration. Dorien and Leon jointly integrated the protected
repository/CD path used for routine deployments. Exact fresh-checkout, unchanged
second-sync, and teardown transcripts were not retained and are not claimed.

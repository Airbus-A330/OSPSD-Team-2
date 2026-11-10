# Container and infrastructure — Issue #68

Status: local implementation only. No Render workspace, cloud resources, or
registry release has been created by this work. Do not interpret a passing local
check as completion of the required teammate deployment exercise.

## Selected approach and ownership

Use one Render image-backed web service, one 1 GB persistent disk, and a
version-controlled Blueprint generated from `infra/render.template.yaml`.
The Dockerfile installs production dependencies from `uv.lock`, including the
shared package's locked revision. Python and uv base images are digest-pinned.
Render receives a prebuilt **linux/amd64** image by digest, not `latest`.
This is a repeatable locked-dependency build, not a claim of bit-identical image
bytes: the build-only Git install and upstream build tooling can change.
Retain and redeploy the exact published image digest instead of rebuilding it.

This follows the MS2 Render proposal without introducing Kubernetes or a second
infrastructure tool. Blueprint resource configuration and resource identity live
in the team's Render workspace; no local Terraform state is needed. Google
remains the event store. The disk stores OAuth refresh state, not events.
One process/instance is intentional: token refresh is serialized between its
threads, while the existing cache is process-local. Do not add workers or scale
out without revisiting credential persistence and locking.

| Responsibility / prerequisite | Current status |
| --- | --- |
| Infrastructure implementation | Xingjian Liu, issue #68 |
| Render account and billing owner | **Unassigned — team must confirm before provisioning** |
| Approved budget | **Not set — do not provision yet** |
| Workspace access | Owner must invite an independent teammate with sufficient provisioning permissions; do not share a login |
| Delivery pipeline and registry publishing | Issue #69; use this Dockerfile and Blueprint, not another deployment path |
| Deployment branch / approved image digest | Team must select; do not assume `master` is the complete MS3 baseline |
| Teardown expectation | Account owner removes the disposable environment after the November 11 demo/verification, unless a specific extension is agreed and recorded |

Cost estimate checked November 9, 2026: the selected `0.5c-512mb` compute is
listed at $7/month, and a 1 GB disk at $0.25/month. **$7.25/month is only the
compute + disk subtotal**, not an approved budget or an all-in quote. Workspace
collaboration/seat fees, bandwidth overages, and registry charges may add cost.
Confirm the live [pricing](https://render.com/pricing) and a spending cap with
the account owner. Free compute is not suitable for this persistent-disk plan.

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

| Variable | Value / handling |
| --- | --- |
| `PORT` | Render listener port; Blueprint sets `10000` |
| `GOOGLE_CALENDAR_ID` | Explicit dedicated test calendar ID, supplied in protected runtime configuration |
| `GOOGLE_CALENDAR_TOKEN_JSON` | Full authorized-user token JSON from an initial local OAuth authorization; secret, supplied only at runtime |
| `GOOGLE_CALENDAR_TOKEN_FILE` | `/var/data/token.json` on the persistent disk |
| `GOOGLE_CALENDAR_NONINTERACTIVE` | `1`; set by the container and hosted startup |
| `CALENDAR_API_TOKEN` | Random, at least 32 ASCII characters without whitespace; share securely with authorized testers and the #69 smoke-check secret store |

Complete the initial browser authorization locally using [PROVIDER.md](PROVIDER.md)
with the dedicated Google test calendar, the Calendar events scope, and an account
allowed to access that calendar. Supply the resulting authorized-user JSON
(including `client_id`, `client_secret`, and `refresh_token`) through Render's
protected environment inputs. Do not paste it into GitHub, chat, commands, or logs.
The hosted service does not need the separate desktop OAuth client JSON file:
the authorized-user JSON already contains the refresh-client information.

On first startup, the valid seed is written to the persistent file with mode
0600. Subsequent starts preserve the existing token, even if the seed is stale.
Startup checks parse the credentials and verify storage access without contacting
Google. Refresh happens during provider use, under a thread lock, with atomic
file replacement. Expired/revoked authorization requires an operator to reauthorize;
it never triggers a browser in the hosted process. Rotation requires stopping
traffic, securely replacing the persistent token and seed, then redeploying.
Do not print their contents for diagnosis.

Verify the disk is writable by UID/GID 10001 on the selected platform. A mount
permission problem deliberately fails startup. If the platform requires initial
ownership setup, the account operator must set that directory's ownership once;
do not solve it by running the service as root or making tokens world-readable.
This platform-specific check remains part of fresh-checkout acceptance.

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
   image digest, region, instance count, disk/mount, plan and runtime variables.
   Use Render's new-Blueprint change preview on initial creation. For updates,
   review the current workspace resource configuration as well as the versioned
   diff before Manual Sync. Schema validation alone is **not** a cloud-state plan.
   Record the proposed changes before applying; stop if resource replacement or
   additional cost is unexpected.

## Provision, shared state and repeat application

After account owner, budget, access and deployment authorization are confirmed:

1. In the intended shared workspace, create **one** Blueprint linked to the
   approved repository branch, with path `infra/render.yaml`. Review Render's
   proposed resources before deploying. Supply the three `sync: false` inputs
   from the runtime configuration table through Render's protected UI.
2. Disable Blueprint **Auto Sync** manually in its Settings. Render's
   [Blueprint reference](https://render.com/docs/blueprint-spec#autodeploytrigger)
   states that `autoDeployTrigger` has no effect for prebuilt-image services, so
   the template omits it. Keep Blueprint Auto Sync off until #69 defines the
   reviewed delivery workflow.
3. Verify the service/disk are owned by that Blueprint, and record their IDs,
   Blueprint link, applied source commit, image digest and authorized operators.
   These mappings and current configuration are the protected/shared IaC state.
   Grant a teammate workspace access and verify they can inspect/manage it.
   A setup only accessible to the original developer does not pass acceptance.
4. Verify `/readyz`, unauthenticated access rejection, and an authenticated GET
   through the deployed shared Calendar API against the dedicated Google calendar.
   Follow [HW2_MS2_GET_VERIFICATION.md](HW2_MS2_GET_VERIFICATION.md) for the
   successful/missing-event checks, adding the deployment authorization header.
   Record statuses and release identity, not response payloads or private IDs.
5. Use **Manual Sync on the same Blueprint** with the unchanged file/image.
   Do not create another Blueprint. Confirm resource IDs and disk identity remain
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
3. In the workspace, explicitly delete the now-unmanaged test service and its
   persistent disk. Confirm the disk and service are absent and billing has stopped.
   Merely deleting a managed service can cause a later sync to recreate it.
4. Remove the unused Blueprint, protected runtime values, registry pull/deploy
   credentials and temporary tester access if no longer needed. Revoke the
   dedicated Google authorization and delete only test-owned Calendar data.
5. Clean up disposable published images according to #69's retention policy.
   Record completion time, operator and resource inventory; never save tokens,
   raw plans containing secrets or unredacted environment exports as evidence.

Cloud deletion is not performed by any local Makefile target.

## Handoff and remaining verification

For #69: build `Dockerfile` once for linux/amd64, publish and retain the digest,
render the same Blueprint, inject the runtime values separately, then smoke-test
with the deployment bearer token. Keep exactly one instance/worker. Image rollback
does not roll back the persistent token file or Google Calendar writes. Do not
allow a later Blueprint sync to accidentally reinstate an obsolete image digest.
The deployment pipeline, rollback exercise, telemetry and SLOs belong to their
respective issues; they are not implemented here.

Before marking #68 complete, attach evidence from someone other than the
infrastructure author: fresh checkout, platform-aware validation/change preview,
provisioned resource identities, authenticated live API reachability, unchanged
second apply, and complete teardown. Also fill the account-owner and budget
fields above. All of those external checks remain pending.

References: [Blueprint management](https://render.com/docs/infrastructure-as-code),
[Blueprint fields/validation](https://render.com/docs/blueprint-spec),
[prebuilt images](https://render.com/docs/deploying-an-image),
[persistent disks](https://render.com/docs/disks), and
[runtime secrets](https://render.com/docs/configure-environment-variables).

## Local verification record — 2026-11-09

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
macOS; native Windows pytest still needs teammate confirmation. Remote CI for
these fixes remains pending until they are committed and pushed.

### Issue #68 acceptance criteria, in issue order

PASS below refers only to the stated local evidence. Cloud results are not inferred.

| # | Criterion | Status | Evidence or remaining step |
| --- | --- | --- | --- |
| 1 | Reproducible deployable artifact | PASS | Pinned bases, locked install, successful linux/amd64 build and runtime check |
| 2 | Locked application dependencies | PASS | `uv sync --locked --no-dev --no-editable`; lockfile unchanged |
| 3 | No credentials/environment secrets in artifact | PASS | Allowlisted build context, explicit copies, no secret build inputs |
| 4 | Version-controlled IaC | PARTIAL | Template/generator committed and pushed in `fcc8858`; digest-specific `infra/render.yaml` still needs generation, review and application |
| 5 | Hosting/IaC tools and rationale documented | PASS | Selected approach above |
| 6 | Preview before apply | PARTIAL | Template/schema and review procedure ready; actual workspace preview pending |
| 7 | Unchanged reapply avoids duplicates/replacement | PARTIAL | Stable resource names/digest; actual second sync pending |
| 8 | Protected/shared infrastructure state | NOT COMPLETED | Requires shared Render workspace, access grants and identity verification |
| 9 | Protected runtime Google credentials | PARTIAL | Runtime-only seed/persistence implemented; actual platform secret configuration pending |
| 10 | Validate config during startup | PASS | Hosted lifecycle and failure tests |
| 11 | Clear sanitized missing-config failure | PASS | Unit and actual-container checks |
| 12 | Health/readiness endpoint | PASS | `/healthz`, `/readyz` in hosted entry point |
| 13 | Temporary Google outage avoids restart loop | PASS | Provider-independent async probes; controlled 503 leaves readiness healthy |
| 14 | Manual prerequisites documented | PASS | Accounts, authorization, permissions, image publishing and disk access |
| 15 | Expected cost/free-tier assumptions | PASS | Subtotal, extra charges and pending budget clearly distinguished |
| 16 | Actual account owner documented | NOT COMPLETED | User confirmed owner is not yet assigned |
| 17 | Teardown date/cleanup expectation | PASS | Remove after Nov 11 demo/verification unless extension agreed |
| 18 | Complete teardown instructions | PASS | Unmanage, delete service/disk, remove secrets/access and verify inventory |
| 19 | Independent teammate provisions fresh checkout | NOT COMPLETED | External acceptance exercise pending |
| 20 | Teammate reaches deployed shared API | NOT COMPLETED | No cloud deployment or live-provider run in this task |
| 21 | Second actual IaC apply has no unexpected change | NOT COMPLETED | Repeat-generation test is not evidence of cloud reapply |
| 22 | Teammate tears down from documentation | NOT COMPLETED | External acceptance exercise pending |
| 23 | No secrets in source/build/logs/plans/CI artifacts | PARTIAL | Local checks used synthetic fixtures; real cloud/CI handling remains to verify |
| 24 | Required CI checks pass | PASS at `fcc8858` | Six GitHub Build/Format/Tests checks passed; subsequent review fixes require a new CI run after push |

# Deployment procedure

This document is the operator procedure for building and deploying Team 2's
service. It contains no claim that a future Milestone 2 release was deployed.
Execution records belong under `docs/evidence/` and are indexed by
[READINESS.md](READINESS.md). The former mixed HW2 procedure and verification log
is preserved as [historical evidence](DEPLOYMENT_HISTORY.md).

## Ownership and boundaries

- Leon Liu (`LeonLiu0204`) owns direct Render account access.
- Reviewed team deployments use the protected GitHub Delivery workflow.
- Images are immutable GHCR digest references.
- Provider credentials and deployment tokens are protected runtime settings;
  they are never built into the image or committed.
- Render's managed service/Blueprint state and version-controlled configuration
  avoid local-machine-only infrastructure state.

## Prerequisites

1. Complete the repository setup in [README.md](../README.md#quick-start).
2. Install Docker for container checks and GNU Make for canonical targets.
3. Obtain approved access to the target GitHub environment and Render service.
4. Configure the protected variables and secrets listed in
   [HW3_DEPLOYMENT.md](HW3_DEPLOYMENT.md). Do not place them in shell history or
   repository files.
5. Confirm the target is disposable or approved for the intended release.

## Validate locally

```bash
uv sync --locked
make check
make conformance
make infra-check
make container-build
make container-check
git diff --check
```

`make infra-check` renders the Blueprint with a synthetic digest and validates
its schema. It does not apply infrastructure or prove runtime configuration.

## Preview configuration

Render an exact proposed image without exposing secrets:

```bash
uv run --locked python scripts/render_blueprint.py \
  --image ghcr.io/airbus-a330/ospsd-team-2@sha256:<64-hex-digest>
```

Review service name, plan, region, instance count, health path, image digest, and
environment-variable names. Save the sanitized rendered configuration and review
result with the release evidence. Never save secret values or an authenticated
API response.

## Deploy through Delivery

Normal deployment is performed by `.github/workflows/delivery.yml`. It runs the
required checks, builds and tests one image, publishes it, resolves the immutable
digest, deploys that exact digest, and runs the canonical smoke/cleanup sequence.
Its current automatic trigger is `hw3-ms1-submission`; the release owner must
review and change that trigger deliberately for the Milestone 2 release branch.
Manual rollback or a disposable exercise supplies an already retained digest; it
must not rebuild the artifact.

Follow [DELIVERY.md](DELIVERY.md) for environment setup, dispatch, concurrency,
failure reconciliation, and rollback.

## Verify the deployed release

For the exact deployed candidate, retain:

- full source SHA and release/tag;
- Delivery run URL/ID and job result;
- immutable image digest and Render deployment ID;
- deployment timestamp and environment;
- `/healthz` and `/readyz` output;
- product smoke output and cleanup result;
- deployed UI/agent/API URLs;
- one correlated deployed request/run across interface, agent, API, and provider;
- sanitized artifacts proving the claimed results.

Use the template in [evidence/README.md](evidence/README.md). A local test, an old
dashboard sample, or a procedure is not deployed-release evidence.

## Repeat-apply check

After the initial apply/synchronization, apply the same reviewed configuration a
second time. Save the platform output that explicitly shows no unintended
replacement or duplicate resource. A prose statement that it was repeated is
not sufficient evidence.

## Teardown

Before teardown, confirm the release owner has retained all required evidence and
any required database backup. Then:

1. disable deployment triggers;
2. delete the Render service through the approved account;
3. revoke Render, model, provider, and test-user credentials;
4. remove test provider records owned by Team 2;
5. apply the documented GHCR retention decision;
6. remove or archive observability resources according to the dated operations
   plan;
7. record completion, operator, timestamp, affected resources, and exceptions.

Never destroy shared resources or another team's data. Planned dates and owners
must be recorded in [OPERATIONS.md](OPERATIONS.md) before release.

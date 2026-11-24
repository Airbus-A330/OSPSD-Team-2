# Cloud Storage integration (#82 / #84)

## Dependencies and selection

The API service installs Team 3 Dropbox and Team 6 S3 implementations as Python packages. It does
not call either team's hosted API or contain a copy of its provider code. The
workflow-facing boundary is `cloud_storage_api.DocumentStorage` and its
`FileInfo`, not Team 3's older `Client` interface or Dropbox SDK types.

| Package | Repository / package directory | Verified tag | Resolved commit | Package version |
|---|---|---|---|---|
| `cloud-storage-api` | [authoritative contract](https://github.com/Dayana20/ospsd26-cloud-storage/tree/0.3.1/src/cloud_storage_api) | `0.3.1` | `664afc92f7cc0b2ee51cde6ddfa088cc3b37206c` | `0.2.0` |
| `dropbox-client-impl` | [Team 3 implementation](https://github.com/Shreyas191/OSPSD-Team-3/tree/v0.3.0/src/dropbox_client_impl) | `v0.3.0` | `fde60d4fb648df6defb918ff815fe940c525adc7` | `0.1.0` |
| `cloud-storage-client-api` | [Team 3 internal dependency](https://github.com/Shreyas191/OSPSD-Team-3/tree/v0.3.0/src/cloud_storage_client_api) | `v0.3.0` | `fde60d4fb648df6defb918ff815fe940c525adc7` | `0.1.0` |
| `storage-service` | [Team 6 implementation](https://github.com/FaizalJnu/OSPSD-TEAM-6/tree/v0.2.0) | `v0.2.0` | `b021b36f6084f3246cdd8ce628fa7380faad1876` | `0.2.0` |

Tags were checked against Git refs, not inferred from package versions. All
listed packages support Python 3.12. Root `tool.uv.sources` explicitly locates the
transitive `cloud-storage-client-api`: a consumer cannot rely on the dependency
repository's workspace source settings. `uv.lock` records exact commits and
hashes, including Dropbox SDK `12.2.5`. Existing locked packages were retained.
The existing Docker build installs these runtime dependencies via
`uv sync --locked --no-dev --no-editable`; no delivery changes are needed here.

Historical candidate review (2026-11-16; Team 6 findings superseded by v0.2.0 below):

- Team 3's default `main` contains the earlier interface. Tagged `v0.3.0`
  exports `DropboxDocumentStorage(DocumentStorage)` and is the selected release.
  Its package README, metadata, authentication code, exports, implementation,
  and `test_document_storage.py` were inspected before integration.
- [Team 1](https://github.com/Dayana20/sandbox/tree/v1.1.0) has no `[project]`
  metadata at its latest tag `v1.1.0`; its `app` package also collides with
  ours. It exposes a local `upload`/`FileResource` contract rather than this
  shared contract. It is not selected or adapted locally.
- [Team 6](https://github.com/FaizalJnu/OSPSD-TEAM-6/tree/v0.1.0) declares
  Python `>=3.13`, FastAPI `>=0.142.2`, and Uvicorn `>=0.54.0`, incompatible
  with our Python/FastAPI/Uvicorn pins. This tag uses its own `StorageClient`
  rather than `DocumentStorage`. It is not selected or patched locally.

These candidate compatibility findings are reproducible without credentials:
check out those exact tags, inspect `pyproject.toml`, and compare Team 1's
`app/providers/base.py` and Team 6's `src/storage_service/storage/base.py` with
the authoritative contract. No mismatch was found in Team 3's exercised
create/download/conflict path. Other operations are not claimed verified.
No external issue or message has been submitted on another team's behalf.

Rechecked for #84 on 2026-11-17: those are still the latest published tags.
[Team 1's tagged interface](https://github.com/Dayana20/sandbox/blob/v1.1.0/app/providers/base.py)
defines `upload(path, content) -> FileResource` under its top-level `app`
namespace, not shared `DocumentStorage.create(path, content) -> FileInfo`.
[Team 6's tagged interface](https://github.com/FaizalJnu/OSPSD-TEAM-6/blob/v0.1.0/src/storage_service/storage/base.py)
defines `put(key, stream, content_type)`, which creates **or overwrites**, rather
than the shared create-only operation. Thus renaming a method or ignoring the
Python constraint would not establish compatible semantics. Either team needs
a compatible, installable release/adapter behind the shared contract before
#84's genuine different-team swap can be verified. Controlled workflow mode is
not a substitute. No upstream package or dependency constraints were modified.

## Construction and credentials

Set `STORAGE_IMPLEMENTATION=team3` (Dropbox) or `team6` (S3) explicitly.
Selection follows the existing `os.environ` configuration pattern.
Missing, blank, misspelled, or unsupported values fail before credential loading.
There is no fallback to another account, provider, or in-memory implementation.

`app.storage_composition.get_document_storage` is a FastAPI generator dependency
yielding `DocumentStorage`. It constructs Team 3's `DropboxDocumentStorage` over
Team 3's authenticated client. Credentials come from Team 3's existing
[authentication setup](https://github.com/Shreyas191/OSPSD-Team-3/blob/v0.3.0/src/dropbox_client_impl/README.md#authentication-oauth-20):

| Runtime input | Purpose |
|---|---|
| `DROPBOX_APP_KEY` | Dedicated test-account app key |
| `DROPBOX_APP_SECRET` | App secret, supplied externally |
| `DROPBOX_REFRESH_TOKEN` | Test-account refresh token, supplied externally |
| `DROPBOX_TOKEN_FILE` | Optional local credential-file path; default `.dropbox_token.json` |
| `DROPBOX_ACCESS_TOKEN` | Upstream short-lived local-development fallback |

Use refresh-token environment configuration in hosting. Team 3 resolves the
refresh-token environment value first, then its token file, then the access
token fallback; incomplete refresh-token configuration fails rather than using
the fallback. Its auth module loads `.env` on import. Keep these inputs outside
Git; `.env` and the default Dropbox token file are ignored. Local custom token
files should live outside the checkout. Required scopes and one-time local
OAuth setup are documented in Team 3's README. Do not run interactive login
inside the deployed API. Constructor credential failures are sanitized
`ProviderUnavailableError` before any storage write; retrying setup alone is safe.

Construction makes no provider call. The factory disables the SDK's built-in
5xx and 429 retries through public `clone` arguments and closes its shared
session on normal completion or failure. All SDK-specific construction stays
in this file. Team 6 construction uses a separate selector branch in the same
file; workflow code continues to consume `DocumentStorage`. Installing both
packages does not establish the milestone's different-team live swap evidence.

## Workflow handoff and errors

The workflow owner can inject `DocumentStorage` using
`Depends(get_document_storage)` and call
`create_document(storage, path, content)` from `app.storage`. That helper
depends only on the shared contract and existing Team 2 errors. It creates once
and returns `FileInfo`. For example, saving a fixed UTF-8 meeting summary at
`/hw3-meeting-<stable-workflow-id>.md` returns the document path, size, and revision
for the combined result. The actual scenario and route belong to the workflow
workstream; no new public HTTP route is introduced by #82.

FastAPI resolves generator dependencies before entering the route. If injected
this way, storage construction is a preflight: a configuration/credential error
leaves all workflow writes not attempted. The composed error handler must
attribute that failure to storage setup, separately from a failed create call.

| Shared storage failure | Team 2 error/code | Outcome / recovery |
|---|---|---|
| Invalid request, invalid operation, file too large | `InvalidInputError` / `invalid_input` | Failed; correct input |
| Existing destination | `InvalidInputError` / `invalid_input` | Failed create; inspect existing content, never infer success |
| Missing resource | `NotFoundError` / `not_found` | Failed; inspect configuration/path |
| Permission denied | `PermissionDeniedError` / `access_denied` | Failed; correct access |
| Provider error, unavailable, or other shared storage error | `StorageWriteUncertainError` / `provider_error` | Uncertain; reconcile before retry |

Every write error has `retryable=false`. HW1 has no dedicated conflict/size
code, so those known rejections use its invalid-input category. Provider error
text is discarded. Unexpected programming errors propagate rather than being
disguised as contract failures. `StorageWriteUncertainError` subclasses the
existing `ProviderFailureError`, allowing the workflow to distinguish uncertainty
without exposing Dropbox types. The ordinary shared Calendar HTTP contract is
unchanged. The composed route must render its own approved step-aware messages;
the existing Calendar handlers contain Calendar-specific messages.

For calendar-success/storage-failure, retain the calendar ID, storage path, and
intended bytes; report storage as failed or uncertain and the issue step as not
attempted. If storage succeeded and issue creation fails, retain its `FileInfo`
and mark storage succeeded. Do not rerun completed steps. Neither this helper
nor the shared storage contract persists workflow progress or provides a global
idempotency key. The workflow owner must preserve that state for reconciliation.

A stable path and create-only semantics prevent overwrites and autorenamed
duplicates. They do not prove exactly-once workflow execution: a timeout can
leave the expected file present even though creation raised. Inspect
`get_metadata(path)` and `download(path)` before deciding whether the content
belongs to the original request; never turn every conflict into success or
retry with a fresh random path. There is no automatic rollback or retry here.

## Verification

`tests/test_storage.py` covers shared results, every shared error category,
sanitization, no write retries, and unexpected-error propagation.
`tests/integration/test_storage_package.py` exercises the installed Team 3
package and shared contract with controlled SDK responses, exact byte
roundtrip, invalid paths/configuration, credential failure, session cleanup,
and a committed write with a lost response followed by a conflict. It also
constructs the real package with a controlled token while forbidding network
access. These tests run in ordinary `make test` / `make check`.

Local verification on Windows / Python 3.12.10 / uv 0.12.17 (2026-11-16):

- `uv lock` and `uv sync --locked`: succeeded, all three Git packages built.
- `make check`: passed; Ruff format checked 61 files, Ruff lint passed, mypy
  checked 61 source files, pytest reported **942 passed, 2 skipped**, and both
  compilation and `app.main` import passed. The skips are the two opt-in live
  tests. Pytest reported one Starlette/AnyIO deprecation warning.
- `make conformance`: **54 passed**, with the same deprecation warning.
- `git diff --check`: passed.
- Container build/check not run: Docker is unavailable on this host. No
  infrastructure or delivery configuration was changed.

After explicit authorization to write to the dedicated test account, set the
external credentials above and run:

```bash
STORAGE_IMPLEMENTATION=team3 RUN_LIVE_STORAGE=1 uv run --locked python -m pytest tests/live/test_storage_workflow.py -q -s
```

This opt-in test creates a uniquely named root-level Markdown document, checks
metadata and exact downloaded bytes, verifies duplicate creation is refused,
then deletes a confirmed creation and checks absence. An uncertain creation is
left for manual reconciliation at the path printed by the test. Do not rerun
until that path has been inspected. This package-level check is separate from
deployed API verification; it does not claim to demonstrate all three verticals.

Provider-backed package verification passed on 2026-11-16 after the user
authorized test-account writes and completed the package's OAuth login:

```text
uv run --locked --env-file .env python -m pytest tests/live/test_storage_workflow.py -q -s --tb=no
1 passed, 7 warnings in 5.57s
```

`RUN_LIVE_STORAGE=1` was supplied externally. The run used the configuration
selector and actual Team 3 package against Dropbox. It confirmed creation,
provider metadata, exact downloaded bytes, duplicate refusal with unchanged
content, deletion, and subsequent absence. The seven warnings were Dropbox
SDK `datetime.utcnow()` deprecations. OAuth credentials were saved locally;
both `.env` and `.dropbox_token.json` were confirmed ignored by Git. No secret
or account identity is retained in this evidence.

This satisfies the provider-backed storage check. The fixed workflow, configured
Team 3 construction, and controlled failed-step behavior are also covered by the
automated composition suite. This package-level run does not establish a hosted
three-provider request or a genuine configuration-only swap to another team's
storage package. Those evidence limits, along with the unrecorded external-team
HW3 design review, are tracked in [HW3_DEPLOYMENT.md](HW3_DEPLOYMENT.md).


## Team 6 v0.2.0 integration (2026-11-23)

The v0.1.0 compatibility findings above are historical. Team 6 v0.2.0 adds the
shared `SharedDocumentStorage` adapter, supports Python >=3.12, and makes its
HTTP server dependencies optional. We install the base package without the
`server` extra. No partner source is copied or patched. `uv.lock` retains the
existing Calendar/Storage contracts and Team 3 package commits. The shared
storage source uses `rev="0.3.1"` instead of `tag="0.3.1"` to match Team 6's
published dependency reference; the resolved commit is unchanged.

The selector calls the public `storage_service.wiring.document_storage_from_env`
constructor. It requires `STORAGE_BACKEND=s3`; memory, missing settings and
whitespace-only credentials fail before construction, with no Dropbox fallback.
Upstream `ConfigError` is sanitized. Construction makes no network request, so
it does not validate access to the real bucket. The workflow still creates
Calendar, then Storage, then Issue Tracker; schemas and shared error mapping are
unchanged. Team 6 returns `id=null` and a path, already permitted by our schema.

| Runtime input | Required value / purpose |
|---|---|
| `STORAGE_IMPLEMENTATION` | `team6` |
| `STORAGE_BACKEND` | `s3` (memory is deliberately rejected) |
| `S3_ENDPOINT` | S3-compatible HTTPS endpoint; OCI format: `https://<namespace>.compat.objectstorage.<region>.oraclecloud.com` |
| `S3_REGION` | Region identifier for that endpoint |
| `S3_BUCKET` | Existing dedicated test bucket |
| `S3_ACCESS_KEY` | Test-account S3 access key / OCI customer secret key ID |
| `S3_SECRET_KEY` | Matching secret; external runtime secret only |
| `MAX_UPLOAD_BYTES` | Optional positive integer; Team 6 defaults to 1 GiB |

Use the storage owner's test-account setup and permissions for the dedicated
bucket. Never commit real configuration. Keep Google and Trello configuration
unchanged. See [upstream configuration](https://github.com/FaizalJnu/OSPSD-TEAM-6/blob/v0.2.0/.env.example).

### Upstream limitations retained by this draft

- Team 6 uses check-then-put for creation, not an atomic create-if-absent. A
  sequential duplicate is rejected, but concurrent writes to the same path can
  race. Use unique paths and serialized test requests; do not claim exactly-once
  creation or unconditional no-overwrite under concurrency.
- Team 6's boto3 configuration uses standard retries with `max_attempts=3`
  (up to four attempts), 5 s connect and 60 s read timeouts. Our workflow calls
  `create` once, but that does **not** mean one outbound write attempt. We do not
  override private SDK state. An uncertain result remains non-retryable at our
  workflow boundary and requires provider reconciliation before any resubmission.
- The public adapter has no close/context-manager method for its underlying S3
  client. We do not reach into private fields to close it. Explicit client
  lifecycle support and configurable retry policy require upstream work before
  claiming parity with the Dropbox request-scoped cleanup/retry guarantees.
- No live OCI credentials, provider run, container deployment or hosted swap
  evidence is included in this local draft.

### Automated and opt-in verification

`tests/integration/test_team6_storage_package.py` uses the installed Team 6
adapter and domain service with only boto3 calls controlled. It checks exact
bytes, nullable IDs, duplicate refusal, configuration rejection, sanitized
errors, real constructor network isolation, and the unchanged HTTP workflow's
success and partial-failure responses. These are integration tests, not real
provider evidence. Existing Dropbox tests continue to run.

After authorization for disposable test-bucket writes, supply the settings above
and run the existing opt-in test:

```bash
STORAGE_IMPLEMENTATION=team6 RUN_LIVE_STORAGE=1 uv run --locked python -m pytest tests/live/test_storage_workflow.py -q -s
```

It verifies create/read/conflict/delete on the selected implementation. Failed
or uncertain creations need reconciliation at the printed path. Do not run it
against a production bucket or treat it as hosted three-provider evidence.

### Configuration-only hosted swap

1. Review and merge the integration, then build/deploy one image containing both
   packages through Delivery. Record its commit, image digest and deployment ID.
2. With `STORAGE_IMPLEMENTATION=team3`, use `make verify-kickoff` against the
   hosted API. Preserve the report and verify the event, Dropbox file bytes and
   Trello card directly. Reconcile and clean up those exact records.
3. Keep that image digest and Calendar/Trello settings unchanged. Change only
   storage configuration to `STORAGE_IMPLEMENTATION=team6`, `STORAGE_BACKEND=s3`
   and the external S3 settings. Record the new deployment ID and selector.
4. Use a fresh verification request/marker/path, then confirm Google Calendar,
   the exact object bytes in the configured S3 bucket, and Trello. Preserve IDs,
   paths and sanitized report; clean up only the exact records from this run.
   Dropbox-specific verification/cleanup scripts cannot verify S3 objects.
5. Link the two reports with the shared image digest and each non-secret
   configuration selection. Only then mark the real configuration-only swap
   complete in the evidence ledger. If a run is uncertain, stop and reconcile;
   do not resend the whole workflow or switch providers to hide the failure.

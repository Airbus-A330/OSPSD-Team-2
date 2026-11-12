# Final human verification record

This is a checklist and evidence template, not proof that an empty section was
completed. Record only observations made against the exact stated revision and
link sanitized evidence. Never paste credentials, private Calendar identifiers,
request bodies, authorization headers, or raw provider payloads.

## A. Full-design review

- Reviewer (not the primary design author):
- Date/time (UTC):
- Revision reviewed:
- What was checked: complete `docs/DESIGN.md`, shared contract mapping, provider
  boundary, failures, state/identity, deployment, observability, reliability,
  tradeoff, and implementation evolution.
- Comments and disposition links:
- Result (approve/request changes):

## B. Independent infrastructure verification

- Verifier (not infrastructure author):
- Date/time (UTC):
- Fresh-checkout exact SHA:
- Help received from infrastructure author:
- `uv sync --locked` and `make check` result:
- `make infra-check` result:
- Preview evidence and proposed changes:
- Provisioned Blueprint/service/resource identifiers:
- Protected runtime values supplied without recording values:
- `/healthz`, `/readyz`, and authenticated shared API result:
- Second unchanged preview/sync result (must show no duplicate/replacement):
- Teardown result and remaining intentional resources:
- Questions or unclear steps discovered:
- Documentation changes made from those questions:
- Result:

Procedure: follow [DEPLOYMENT.md](DEPLOYMENT.md) from a new directory at the exact
SHA. Review the generated digest-specific Blueprint and current Render resource
configuration before the first sync. After successful API verification, repeat
the same generation and sync without changing inputs and record the no-change
result. Then follow the teardown inventory exactly; never delete shared or
non-test resources.

## C. Independent operator exercise

- Verifier (not delivery/infrastructure author):
- Date/time (UTC):
- Revision:
- Start/end time and elapsed minutes:
- What is running:
- Which version/image digest is serving:
- Health evidence:
- Log/trace location found:
- Rollback procedure and known-good digest found:
- Help required:
- Result (all five answered from documentation within about ten minutes):

Use only [OPERATIONS.md](OPERATIONS.md) and the canonical documents it links; do
not inspect source code or workflow implementation during the timed exercise.

## D. Independent telemetry exercise

- Verifier (not instrumentation author):
- Date/time (UTC):
- Environment and release:
- Dashboard URL and evidence-retention location:
- Committed dashboard revision imported/confirmed:
- Latency series visibly separated by operation and outcome:

### Successful provider-backed request

- Operation/status/outcome:
- Sanitized request ID and trace ID:
- Release shown:
- Log-to-trace correlation:
- Provider child span and timing explanation:

### Provider failure

- Approved disposable setup:
- Operation/status/outcome:
- Sanitized request ID and trace ID:
- Release shown:
- Log-to-trace correlation:
- Provider child span and timing explanation:

### Invalid request

- Request shape without sensitive values:
- Operation/status/outcome:
- Sanitized request ID and trace ID:
- Release shown:
- Explanation of why no provider child span is expected:

- Verifier's caller-vs-service-vs-provider explanation:
- Cleanup/restoration confirmation:
- Result:

Safe procedure: use a synthetic event in the disposable test calendar for the
successful request. For provider denial, only with the calendar owner's approval,
use a disposable calendar on which the service identity has read-only permission
and attempt a synthetic Create; expect 403 `access_denied`, a provider child span,
and no created event. Restore the disposable permission fixture afterward. For
invalid input, submit a blank-title Create; expect 422 `invalid_input` and no
provider child span. Do not revoke production credentials or alter production
permissions to manufacture a failure.

## E. Telemetry privacy inspection

- Reviewer:
- Date/time (UTC):
- Sanitized exported log artifact/link:
- Sanitized exported trace artifact/link:
- No OAuth/API/bearer token:
- No authorization header or credential material:
- No request/response body, title, description, or provider payload:
- No raw event ID or raw URL where prohibited:
- Metric labels limited to bounded operation/outcome/release dimensions:
- Any collector-added fields reviewed:
- Result:

## F. Final exact-commit verification

- Final SHA:
- Required CI run/check URLs:
- Full test result:
- Shared conformance result:
- Infrastructure validation result:
- Reliability-rule validation result:
- Delivery run and immutable image digest:
- Canonical smoke and cleanup result:
- Annotated tag:
- GitHub Release URL:
- Submission SHA matches release/tag:
- Result:

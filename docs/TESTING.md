# Testing Strategy

This document records what the project tests and why.

Repository-wide testing rules are defined in `../AGENTS.md`.

## Test Layers

### Unit
Small, deterministic tests of individual behavior.

### Integration
Tests of meaningful boundaries between multiple components.

### Real Provider / E2E
Verification against the actual provider.

## Provider Substitution

For Level 4, fast application tests must replace the real provider at the
`EventProvider` boundary. These tests must require neither Google credentials
nor live network access. Patching only the Google SDK network call does not
demonstrate that application logic can accept a substitute for the provider
interface.

`tests/test_provider_substitution.py` defines `ControlledEventProvider`, a small
mapping from requested identifiers to configured `Event` instances or explicitly
configured service errors. Its fixture returns `EventProvider`, so mypy checks
structural compatibility with the frozen interface without requiring inheritance
or Google SDK types.

Application tests pass the controlled provider to `app.events.get_event` and
verify two distinct identifiers and repeated reads without state changes. HTTP
tests override `app.main.get_event_provider`, the same FastAPI dependency used
by normal execution, and verify the complete response and unchanged timestamps.
Pytest's `monkeypatch` restores the dependency override after each test, including
on failure. The tests patch neither application behavior nor Google SDK calls.

The fixture creates fresh events per test and can be configured with any required
identifier-to-outcome mapping. It contains no authentication, network access, or
Google behavior simulation. Missing-resource outcomes must be configured explicitly;
incidental missing-key behavior is not a promised application error contract.
Real-provider verification remains separate and documented in [PROVIDER.md](PROVIDER.md).

## Google Provider Tests

`tests/test_google_calendar_provider.py` tests the concrete
`GoogleCalendarProvider` with a controlled SDK client. Its fourteen cases cover:

- Two calendar/event ID pairs: construction makes no SDK calls, retrieval uses
  the supplied identifiers, and the result is an `Event` with exactly the four
  public fields and unchanged timestamp strings.
- Google HTTP errors, built with Google's structured error response shape:
  404 (`notFound`) translates to `NotFoundError`; 403 translates to
  `PermissionDeniedError` for a permission reason or no structured reason, and
  to `ProviderFailureError` when the machine-readable reason reports a quota
  or rate limit (`rateLimitExceeded`, `userRateLimitExceeded`,
  `quotaExceeded`); 429, 400, and 500 also translate to
  `ProviderFailureError`. The raised service error is not the SDK exception,
  contains no provider error text, and does not retain the provider exception
  as its cause.
- Transport failures: an `httplib2` transport error and a Google
  authentication `TransportError` raised while executing the request each
  translate to `ProviderFailureError`, likewise without retaining the
  original exception as the cause.
- An unsupported all-day response: translation raises `KeyError` instead of
  returning raw Google data or inventing timestamps.

These tests run without credentials or network access. Existing mapping and
model tests cover additional missing-field and invalid-type cases. The separate
HTTP integration test covers controlled provider substitution; live Google
connectivity is documented in `PROVIDER.md`.

## Level 5 HTTP Failures (#39)

`tests/test_http_errors.py` sends requests through FastAPI and the application
operation. A controlled `EventProvider` supplies the four shared service failures;
tests assert exact HTTP statuses, codes, fixed messages, and the complete JSON
shape defined in [CONTRACT.md](CONTRACT.md). Synthetic exception and authorization
values must not appear in responses or logs. Each expected failure produces one
warning containing operation, error category, status, and provider involvement,
without exception or stack information.

Additional cases verify that:

- Whitespace-only IDs return 400 before Google client construction or OAuth.
- Valid IDs containing surrounding spaces or Unicode reach the provider unchanged,
  return the four public Event fields, and produce no failure warning.
- Request-scoped clients close on missing-event, permission, and provider failures.
- A shared service failure during provider setup is rendered and logged.
- Unexpected programming errors and unsupported base `ServiceError` instances
  are not disguised as a supported public error category.

The tests require neither credentials nor live network. Production composition
checks replace client construction and the concrete provider with controlled
objects. They do not verify Google-specific exception translation, which belongs
to #38, or live-provider failures. Existing tests retain the unmatched-route 404s
for `/events` and `/events/` and the Levels 1–4 success/substitution guarantees.

## Integrated Level 5 Verification (#40)

`tests/test_provider_substitution.py::test_http_failures_do_not_affect_subsequent_retrieval`
extends the Level 4 substitution tests with a repeated-request workflow through the
same FastAPI app and controlled provider:

1. Retrieve an existing event: 200 and exactly its four public fields.
2. Request a whitespace-only ID: 400 and the fixed `invalid_input` response.
3. Request an explicitly configured failure: 404 `not_found`, 403
   `permission_denied`, or 502 `provider_error`, with the exact public body.
4. Retrieve the original event again: 200 and the unchanged response.

The three parameterized cases verify that locally rejected and provider-failed
requests do not prevent subsequent successful retrieval. They assert the public
contract, not SDK calls or exception internals. Overrides are restored by
`monkeypatch`. The focused validation, HTTP mapping/logging, and Google translation
tests remain owned by #37, #39, and #38; this workflow does not duplicate their
unit cases or establish live Google behavior.

Run `make test` for all fast tests, or select this workflow with:

```bash
uv run --locked python -m pytest tests/test_provider_substitution.py -k test_http_failures_do_not_affect_subsequent_retrieval
```

### Defect-detection evidence

On the #40 branch based on `882d396`, the `NotFoundError` HTTP mapping was
temporarily changed from 404 to 200. The workflow's `[not_found]` case failed
at `assert response.status_code == status` with `assert 200 == 404` (one failed).
After restoring the 404 mapping, the same case passed (one passed). This protects
the requirement that a failed lookup must not be reported as successful. The
mutation was not committed; the PR records the exact command and results.

Real-provider verification: **NOT PERFORMED**. Google failure translation remains
separate (#38); passing controlled-provider tests is not final live-provider or
release verification.

## CI

Required GitHub Actions checks:

- Build
- Format
- Tests

Normal CI must not require provider credentials.

## Feature Test Matrix

| Feature / Contract | Unit | Integration | Real Provider | Known Gaps |
|---|---:|---:|---:|---|
| Public Event model | Yes | | | `tests/test_event_model.py` covers construction, serialization, required string fields, and timestamp preservation |
| Service error types | Yes | | | `tests/test_errors.py` verifies exception construction and catching through `ServiceError`; provider translation and HTTP rendering remain separate |
| Local event-ID validation | Yes | | | `tests/test_provider_substitution.py` verifies blank IDs never invoke the provider and nonblank IDs pass unchanged, including whitespace and unusual characters |
| Google Calendar client construction | Yes | | Manual | Automated tests mock OAuth and API client construction |
| FastAPI event endpoint | | Yes | Manual | `tests/test_provider_substitution.py` overrides `get_event_provider` with a controlled provider and verifies the exact four-field response; live verification is documented in `PROVIDER.md` |
| Level 5 HTTP failures | | Yes | Not verified | Exact shared-error responses, sanitized logs, and repeated success/failure/recovery through controlled provider substitution; Google-specific translation and live failures are separate |
| Provider composition | Yes | | | `tests/test_event_routes.py` verifies configured and default calendar IDs with a controlled SDK client |
| Google event translation | Yes | | | Synthetic timed-event fixtures; all-day and sparse responses are unsupported |
| Google event retrieval | Yes | Yes | Manual | Provider HTTP errors translate to service errors (#38); live failure verification requires team credentials |
| `EventProvider` contract | Yes | Yes | | `tests/test_event_provider.py` verifies structural compatibility and domain input/output; the HTTP test verifies substitution through `app/providers.py` |
| Google provider implementation | Yes | | Manual | Provider unit tests use a controlled SDK client; live timed-event retrieval is documented in `PROVIDER.md` |
| Application event retrieval through `EventProvider` | Yes | Yes | | Controlled events verify identifier selection, response preservation, and repeated reads |
| Controlled provider substitution | Yes | Yes | No | `tests/test_provider_substitution.py` uses a configurable provider through application arguments and `app.dependency_overrides` |

Update this table whenever meaningful behavior is added.

Event route tests also cover `/events` and `/events/` without the required ID.
Their 404 responses reflect unmatched routes, not a lookup for a nonexistent event.

## Commands

Run the complete local verification suite from the repository root:

```bash
make check
```

Real-provider authentication and end-to-end verification are documented in
`PROVIDER.md`.

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
`GoogleCalendarProvider` with a controlled SDK client. Its seventeen cases cover:

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

## Event Creation Tests

`tests/test_create_event.py` verifies the provider-independent application and
HTTP creation path. It checks the 201 response, provider-generated identifier,
complete returned values, and the controlled provider's recorded write. Focused
cases reject a blank title, invalid time ordering, timestamps without UTC
offsets, and missing time fields before a provider write. Permission denial and
provider failure use the shared public error shape and sanitized logging.

`tests/test_google_calendar_provider.py` verifies that creation uses Google
`events.insert` with only `summary`, `start.dateTime`, and `end.dateTime`, then
translates the provider result into `Event`. Controlled Google 403 and 500
responses verify service-error translation without credentials or network.

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
to #38, or live-provider failures. Levels 1–4 GET-one success/substitution
guarantees remain. Under #51, `/events` is now the listing route and `/events/`
redirects to it rather than representing an unmatched event-ID route.

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

## Event Listing (#51, Maksym)

The existing controlled provider in `tests/test_provider_substitution.py` now
implements `list_events` as well as GET-one. HTTP cases verify the default limit
of 10, boundaries 1 and 100, exact public Event fields, empty calendars, rejection
of malformed/out-of-range limits before client setup, and shared provider-failure
responses with `list_events` log context. Application tests also check bounds for
non-HTTP callers. The old `/events` missing-ID 404 test is replaced because that
path intentionally becomes the collection operation.

`tests/test_google_calendar_listing.py` controls the SDK to verify calendar/limit
parameters, recurrence expansion, bounded translation, hidden page tokens, empty
pages, service-error translation, and unsupported all-day responses.
`tests/test_event_routes.py` exercises the real listing composition with a mocked
SDK client and confirms request-scoped cleanup. Get-only test doubles add the
listing method solely to stay compatible with the expanded shared protocol.

Run `make check` for the full suite, or focus on listing:

```bash
uv run --locked python -m pytest tests/test_google_calendar_listing.py tests/test_provider_substitution.py tests/test_event_routes.py -k 'list or collection'
```

Tests need no credentials, live network, or sleeps. Live listing verification is
**NOT PERFORMED**; its manual procedure is in
[PROVIDER.md](PROVIDER.md#list-events-verification).

## CI

Required GitHub Actions checks:

- Build
- Format
- Tests

Normal CI must not require provider credentials.

## Feature Test Matrix

| Feature / Contract | Unit | Integration | Real Provider | Known Gaps |
|---|---:|---:|---:|---|
| Event listing | Yes | Yes | Not verified | Default/bounded limits, empty pages, fixed errors, SDK translation, and client cleanup; see the listing section above |
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
| Create event | Yes | Yes | Manual required | Controlled writes verify validation, the 201 response, returned values, provider failures, and Google request/response translation; live steps are in `PROVIDER.md` |

Update this table whenever meaningful behavior is added.

Event route tests also cover `/events` and `/events/` without the required ID.
Their 404 responses reflect unmatched routes, not a lookup for a nonexistent event.

## Commands

### PUT replacement (#51, Nicolas Ollivier)

`tests/test_provider_substitution.py` now gives the controlled provider a
`replace_event` operation and records replacement attempts. PUT tests check:

- Complete replacement, exact response, read-back state, a repeated replacement,
  and preservation of another event.
- Missing editable fields and invalid title/types/timestamps/intervals rejected
  before provider setup or writes. Equal instants across different offsets are
  invalid; valid different offsets are compared chronologically. Blank IDs and
  malformed/missing JSON are also rejected locally.
- Missing events are not created; shared missing/permission/provider failures
  retain their public error envelopes and log the PUT operation.
- A provider accepting a write and losing the response returns 502 without retry;
  subsequent GET reveals the changed state.

`tests/test_google_calendar_provider.py` checks full `events.update` construction,
domain response translation, HTTP/transport error mapping, and no retry. Existing
GET-only doubles receive only the method needed to satisfy the expanded protocol;
their retrieval behavior is unchanged. All fast tests are credential/network-free.
Live PUT verification remains outstanding; follow [PROVIDER.md](PROVIDER.md).

Defect-detection evidence: temporarily changing the interval rejection from
`end <= start` to `end < start` allowed equal instants at different offsets.
`test_invalid_put_values_rejected_before_provider_setup[changes6]` failed with
`AssertionError: Invalid replacement must not set up or call a provider`.
The strict comparison was restored before the final passing verification.

```bash
uv run --locked python -m pytest tests/test_provider_substitution.py -k put
uv run --locked python -m pytest tests/test_google_calendar_provider.py -k replace
```

Run the complete local verification suite from the repository root:

```bash
make check
```

Real-provider authentication and end-to-end verification are documented in
`PROVIDER.md`.

## Partial update coverage — Yasmin (#51)

PATCH cases in `tests/test_provider_substitution.py` exercise the public route
with the existing controlled provider. They check persisted title-only and time
updates, omitted-field preservation, malformed/empty bodies, blank IDs, and
single-time changes that would invalidate the stored interval. Rejected local
inputs cannot construct a provider; invalid combined intervals cannot write.
Missing-resource, permission, and provider failures use the shared safe envelope
and operation log context. Existing GET/list/create/replace tests remain intact.

`tests/test_google_calendar_patch.py` checks exact sparse Google request bodies,
translated domain responses, HTTP/transport failure mapping, unsupported responses,
and no retries. All these tests are credential-free and network-free. Real-provider
PATCH verification remains outstanding; use `PROVIDER.md` before final release.

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
`GoogleCalendarProvider` with a controlled SDK client. Its focused cases cover:

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
- Transport failures: `httplib2`, Google authentication, socket timeout, and
  connection-reset errors raised while executing requests translate to
  `ProviderFailureError`, without retaining the original exception as the
  cause.
- Unsupported all-day and malformed create responses become
  `ProviderFailureError` instead of returning raw Google data, leaking mapping
  exceptions, or inventing fields.

These tests run without credentials or network access. Existing mapping and
model tests cover additional missing-field and invalid-type cases. The separate
HTTP integration tests cover controlled provider substitution and prove malformed
GET/POST Google responses render the shared 502 envelope while closing the
request-scoped client. Live Google connectivity is documented in `PROVIDER.md`.

## Event Deletion Tests — Xingjian Liu

`tests/test_delete_event.py` exercises DELETE using a stateful controlled
`EventProvider`, with no credentials or network access. It verifies:

- 204 with an empty body, removal of only the target, unchanged neighboring
  events, a subsequent missing-event read, and repeated deletion returning 404.
- Blank-ID rejection before client construction and application-level rejection
  before provider calls; nonblank IDs are forwarded unchanged.
- Exact 404/403/502 envelopes, safe deletion log context, and no automatic retry.
- A lost response can return 502 after the controlled provider has deleted the
  event; the service neither retries nor claims rollback.
- Google calls use the configured calendar and exact ID; Google/transport
  failures become service errors, and request-scoped clients close in both
  success and failure paths.

Google's `410 deleted` reason is covered separately from unrelated 410 errors.
Two regression cases verify that a Google GET response with `status=cancelled`
returns the shared 404 envelope, whether it retains full event fields or only
the identifier. This defect was found during live deletion verification.
Other operation fixtures gain only the required unused deletion method to keep
them compatible with the expanded protocol; their existing assertions remain.

```bash
uv run --locked python -m pytest tests/test_delete_event.py
make check
```

These controlled checks do not establish live Google behavior. Follow
[PROVIDER.md](PROVIDER.md#delete-verification) for separate real-provider evidence.

Local verification on 2026-10-20 found all 26 DELETE lifecycle tests passing.

## Event Creation Tests

`tests/test_create_event.py` verifies the provider-independent application and
HTTP creation path. It checks the 201 response, provider-generated identifier,
complete returned values, and the controlled provider's recorded write. Focused
cases reject a blank title, invalid time ordering, timestamps without UTC
offsets, missing fields, and unknown provider-specific fields before a provider
write. OpenAPI coverage marks the body required. Permission denial and provider
failure use the shared public error shape and sanitized logging.

`tests/test_google_calendar_provider.py` verifies that creation uses Google
`events.insert` with only `summary`, `start.dateTime`, and `end.dateTime`, then
translates the provider result into `Event`. Controlled Google 403 and 500
responses and malformed success payloads verify service-error translation without
credentials or network.

## Event Cache Tests

`tests/test_event_cache.py` uses controlled providers and an injected clock to
verify cache misses and hits, the 60-second expiry boundary, separation by
configured calendar, bounded storage with oldest-entry eviction, and repeated
HTTP responses. Provider call counts prove that unexpired hits avoid another
provider operation and expired entries refresh without sleeping. Separate cases
prove that invalid input and each documented service failure are not cached. A
production-composition test controls the Google SDK boundary and verifies that
two HTTP requests share cached domain data while both request-scoped clients are
still closed. Write-operation cases verify that creation and successful updates
refresh affected entries, deletion removes its entry, uncertain failed writes
do not leave stale values, a blocked read cannot restore an entry after a
concurrent deletion, and listing bypasses the single-event cache.

Gate-controlled HTTP regressions also start reads during DELETE, PUT, and PATCH,
then release those reads both before and after write completion. They cover
successful writes and writes that apply remotely but lose their response. Later
GET requests must observe deletion or updated state. Separate overlapping-write
and delayed-create cases ensure late responses cannot restore older state. A
creation-completion case verifies that an older read cannot overwrite the newly
created value once its provider-generated ID is known. These cases use the actual
cache wrapper and controlled providers, with no sleeps.

`tests/test_http_errors.py` checks malformed JSON syntax and invalid UTF-8 on
POST/PUT/PATCH: the shared 400 envelope, one sanitized failure log, and rejection
before provider setup. Unrelated HTTP errors retain their original status, body,
and headers, including ordinary 404/405 routing responses.

These tests use no credentials, network access, or wall-clock delays.

## Level 5 HTTP Failures

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
objects. They do not verify Google-specific exception translation or live-provider
failures. Levels 1–4 GET-one success/substitution guarantees remain. `/events` is
the listing route and `/events/` redirects to it rather than representing an
unmatched event-ID route.

## Integrated Level 5 Verification

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
`monkeypatch`. Focused validation, HTTP mapping/logging, and Google translation
tests cover their respective boundaries; this workflow does not duplicate those
unit cases or establish live Google behavior.

Run `make test` for all fast tests, or select this workflow with:

```bash
uv run --locked python -m pytest tests/test_provider_substitution.py -k test_http_failures_do_not_affect_subsequent_retrieval
```

### Defect-detection evidence

During defect-detection testing, the `NotFoundError` HTTP mapping was temporarily
changed from 404 to 200. The workflow's `[not_found]` case failed
at `assert response.status_code == status` with `assert 200 == 404` (one failed).
After restoring the 404 mapping, the same case passed (one passed). This protects
the requirement that a failed lookup must not be reported as successful. The
mutation was not committed; the verification record includes the exact command
and results.

Real-provider verification on 2026-10-20 included the public missing-event path:
repeated DELETE and subsequent GET returned the documented 404 envelope. Real
permission denial and provider-outage conditions were not induced; their exact
responses and recovery behavior remain covered by controlled tests.

## Event Listing — Maksym

The existing controlled provider in `tests/test_provider_substitution.py` now
implements `list_events` as well as GET-one. HTTP cases verify the default limit
of 10, boundaries 1 and 100, exact public Event fields, empty calendars, rejection
of malformed/out-of-range limits before client setup, and shared provider-failure
responses with `list_events` log context. Application tests also check bounds for
non-HTTP callers. `GET /events` is the collection operation, while
`GET /events/{event_id}` retrieves one event. `GET /events/` redirects to the
collection route rather than representing a missing event ID.

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

Tests need no credentials, live network, or sleeps. Live listing verification was
completed on 2026-10-20 and is recorded in
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
| Event listing | Yes | Yes | Verified 2026-10-20 | Default/bounded limits, empty pages, fixed errors, SDK translation, and client cleanup; see the listing section above |
| Public Event model | Yes | | | `tests/test_event_model.py` covers construction, serialization, required string fields, and timestamp preservation |
| Service error types | Yes | | | `tests/test_errors.py` verifies exception construction and catching through `ServiceError`; provider translation and HTTP rendering remain separate |
| Local event-ID validation | Yes | | | `tests/test_provider_substitution.py` verifies blank IDs never invoke the provider and nonblank IDs pass unchanged, including whitespace and unusual characters |
| Google Calendar client construction | Yes | Yes | Manual | Automated tests mock OAuth/client construction and translate token-refresh transport failures through the public 502 boundary |
| FastAPI event endpoint | | Yes | Manual | `tests/test_provider_substitution.py` overrides `get_event_provider` with a controlled provider and verifies the exact four-field response; live verification is documented in `PROVIDER.md` |
| Level 5 HTTP failures | | Yes | Missing-event verified 2026-10-20 | Exact shared-error responses, sanitized logs, and repeated success/failure/recovery through controlled provider substitution; permission and outage cases remain controlled-only |
| Provider composition | Yes | | | `tests/test_event_routes.py` verifies configured and default calendar IDs with a controlled SDK client |
| Google event translation | Yes | | | Synthetic timed-event fixtures; all-day and sparse responses are unsupported |
| Google event retrieval | Yes | Yes | Verified | Provider HTTP errors and malformed payloads translate to service errors; live success and missing-event behavior are documented in `PROVIDER.md` |
| `EventProvider` contract | Yes | Yes | | `tests/test_event_provider.py` verifies structural compatibility and domain input/output; the HTTP test verifies substitution through `app/providers.py` |
| Google provider implementation | Yes | | Verified 2026-10-20 | Provider unit tests use a controlled SDK client; all six public operation paths were verified against Google |
| Application event retrieval through `EventProvider` | Yes | Yes | | Controlled events verify identifier selection, response preservation, and repeated reads |
| Controlled provider substitution | Yes | Yes | No | `tests/test_provider_substitution.py` uses a configurable provider through application arguments and `app.dependency_overrides` |
| Create event | Yes | Yes | Verified 2026-10-20 | Controlled writes verify strict validation, the 201 response, returned values, provider failures, and Google request/response translation |
| Replace event | Yes | Yes | Verified 2026-10-20 | Complete replacement, read-back state, strict validation, shared failures, exact Google update request, and translated response |
| Partial update event | Yes | Yes | Verified 2026-10-20 | Sparse updates, omitted-field preservation, resulting interval validation, shared failures, exact Google patch request, and translated response |
| Delete event | Yes | Yes | Verified 2026-10-20 | 26 controlled cases; live create/read/delete/repeat/read-back verified with a disposable event. Permission and provider failures remain controlled-only; see `PROVIDER.md` |
| Successful event caching | Yes | Yes | Not applicable | Controlled providers and a fake clock verify hit, miss, expiry, bounded storage, oldest-entry eviction, calendar isolation, failure behavior, production composition, and unchanged HTTP responses |

Update this table whenever meaningful behavior is added.

Event route tests also cover `/events` and `/events/` without the required ID.
Their 404 responses reflect unmatched routes, not a lookup for a nonexistent event.

## Commands

### PUT Replacement — Nicolas Ollivier

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
Live PUT verification was completed on 2026-10-20 and is recorded in
[PROVIDER.md](PROVIDER.md).

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

## Partial Update Coverage — Yasmin

PATCH cases in `tests/test_provider_substitution.py` exercise the public route
with the existing controlled provider. They check persisted title-only and time
updates, omitted-field preservation, malformed/empty bodies, blank IDs, and
single-time changes that would invalidate the stored interval. Rejected local
inputs cannot construct a provider; invalid combined intervals cannot write.
Missing-resource, permission, and provider failures use the shared safe envelope
and operation log context. Existing GET/list/create/replace tests remain intact.

`tests/test_google_calendar_patch.py` checks exact sparse Google request bodies,
translated domain responses, HTTP/transport failure mapping, unsupported responses,
and no retries. All these tests are credential-free and network-free. Live PATCH
verification was completed on 2026-10-20 and is recorded in `PROVIDER.md`.

## Final endpoint contract regressions

`tests/test_final_provider_contracts.py` runs the real HTTP/application/cache/Google
adapter composition with only the SDK controlled. It checks fresh tombstone
preflights (including a stale active cache entry), no writes after failed
preflight, cancelled write responses, wrong resource identities, unsupported
success payloads across five Event-returning operations, all six error mappings,
and fresh one-sided PATCH interval validation. DELETE accepts an empty SDK result;
an empty LIST page remains valid. Existing SDK tests now configure the active
preflight explicitly so malformed-write tests still reach the write response.

`tests/test_final_endpoint_validation.py` covers non-object/empty/malformed JSON,
invalid UTF-8, required/unknown/null fields, title and timestamp boundaries,
opaque IDs, integer limit boundaries, and rejection before provider setup.
Positive cases preserve Unicode, Z/positive/negative offsets, all nonempty PATCH
field combinations, and unchanged identifiers. Existing cache ordering and
framework 404/405 tests remain part of `make check`.

Before the fix, these regressions failed for tombstone writes, unchecked success
payloads and identities, stale one-sided PATCH state, and decimal `limit=1.0`.
They now pass, including checks for empty provider IDs and cancelled LIST/POST
results. These tests require neither real credentials nor network access.
Real-provider verification is recorded separately in `PROVIDER.md`; mocked SDK
success is not live-provider evidence.

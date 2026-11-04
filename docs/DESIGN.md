# Shared Calendar Contract Migration Design

## Status

This design covers Team 2's first HW2 migration slice: `GET /events/{event_id}`.
It was prepared from the final HW1 service, the HW1 architecture review, and the
[joint Calendar contract](JOINT_CALENDAR_CONTRACT.md) agreed by Teams 2, 5, and
7.

The shared implementation is maintained in the
[`OSPSD-Calendar`](https://github.com/Airbus-A330/OSPSD-Calendar) repository.

The service depends on the immutable shared-package release-candidate tag
[`v0.1.0-rc.1`](https://github.com/Airbus-A330/OSPSD-Calendar/tree/v0.1.0-rc.1),
which resolves to commit `1c1cad7a0732ddb242a05400d8833d94e4422424` and
declares package version `0.1.0`. It does not depend on `master` or another
moving branch.

## Context

The HW1 service has six provider-backed operations, a provider-independent
application boundary, deterministic tests, and an optional read cache. The HW2
contract standardizes four operations, shared request/response models, shared
service errors, and conformance tests across three Calendar teams.

The HW1 review also identified structural debt:

- application and test modules were mostly flat;
- `main.py` combined startup, composition, validation, and routing;
- validators and error rendering communicated through hidden `request.state`
  fields;
- HTTP dependencies repeated validation performed by application functions;
- Google failures were logged only after reaching the HTTP boundary;
- module-level Google helpers had the same names as provider and application
  operations;
- two test modules were named for being "final" rather than for their behavior.

## Goals

1. Consume an immutable shared package release reproducibly.
2. Migrate GET-one as the first complete shared-contract vertical slice.
3. Preserve real Google Calendar retrieval and the existing cache behavior.
4. Keep Google SDK objects and configuration behind the provider boundary.
5. Make HTTP routing, request validation, application behavior, composition,
   and provider integration independently understandable.
6. Log safe Google operation and status context where provider failures occur.
7. Establish a small pattern that later shared-operation migrations can reuse.

## Non-goals

This slice does not standardize Team 2's optional listing or PATCH extensions,
add another real provider, add a dependency-injection framework, redesign the
cache, add retries, or perform a speculative rewrite of every operation.

## Current architecture

The HW1 request flow is:

```text
FastAPI route and validation in main.py
    -> application function in events.py
    -> EventProvider
    -> CachedEventProvider
    -> GoogleCalendarProvider
    -> Google Calendar SDK
```

The boundaries are conceptually sound, but the entry point formerly contained
all routes and validation dependencies. Error presentation depended on
request-local flags written by several functions, and Google exceptions were
translated without a provider-layer log describing the failed operation.

## Target architecture

```text
app/main.py                 application creation and handler registration
    -> app/api/routes.py    thin HTTP routes
    -> app/api/validation.py HTTP-only early validation
    -> app/events.py        provider-independent application behavior
    -> app/providers.py     Team 2 provider extension boundary
    -> app/event_cache.py   optional domain-event cache wrapper
    -> app/google_calendar.py Google SDK adapter and translation

app/composition.py          concrete provider selection and request lifetime
app/http_errors.py          public error rendering and HTTP failure logging
calendar-contract           shared core models, errors, and CalendarService
```

`main.py` no longer owns provider construction, validators, or route functions.
HTTP error rendering derives the operation from the matched route and receives
explicit error context; it does not read validator-written `request.state`
fields. Google failures are logged inside the Google adapter with only the
operation and numeric status when available. Event IDs, provider payloads,
credentials, exception text, and request headers are excluded.

## GET request flow

```text
GET /events/{event_id}
    -> validate_get_request rejects a blank ID before OAuth/client setup
    -> get_event_provider composes a request-scoped Google client
    -> read_event invokes application get_event with the validated ID
    -> CachedEventProvider serves a hit or delegates
    -> GoogleCalendarProvider executes events.get
    -> provider response is translated to the domain Event
    -> FastAPI serializes the shared Event response shape
```

The HTTP dependency is the authoritative blank-ID validation point for this
migrated route. The application operation retains optional validation for
non-HTTP callers, while the route explicitly skips the duplicate check after
the dependency has succeeded.

## Shared API and model mapping

The shared release-candidate tag is pinned and locked with uv. The shared core
will map as follows during the separate application migration:

| Shared package | Team 2 use |
|---|---|
| `Event` | GET/create/replace public response and provider translation |
| `CreateEvent` | shared POST request fields |
| `ReplaceEvent` | shared PUT request fields |
| `CalendarError` / `ErrorCode` | provider-independent failure boundary |
| `CalendarService` | create/get/replace/delete contract |

Team 2's list limit, `EventPatch`, listing, and PATCH methods remain local
extensions. They must not be added to or presented as requirements of the
shared core. Compatibility aliases may be retained briefly if needed to keep a
small migration diff, but validation and models must have one implementation.

## Failure behavior

The shared contract requires `invalid_input`, `not_found`, `access_denied`,
`provider_error`, and `provider_unavailable`, including required `retryable` in
the HTTP error body. HTTP status mapping remains a Team 2 HTTP concern;
provider code raises shared errors rather than returning HTTP responses.

Google HTTP and transport failures are logged before translation using safe
operation context. HTTP logging records the public operation, shared code,
status, and whether the error explicitly indicates provider involvement. No
layer logs credentials, authorization headers, raw payloads, event IDs, or
provider error messages.

## Operational considerations

Google OAuth files remain local and ignored. Each request owns and closes its
Google client because its HTTP transport is not safe to share across worker
threads. The process-local cache continues to share domain `Event` values only;
it does not retain SDK objects. The migration does not change cache TTL,
capacity, invalidation, or concurrency behavior.

## Testing

Fast tests continue to replace the provider or SDK boundary and require no
credentials or network. The migrated slice needs evidence at four levels:

1. shared-package model and error tests in the shared repository;
2. Team 2 application tests using a controlled service/provider;
3. HTTP tests for exact GET success and shared error responses;
4. Google-adapter tests for SDK calls, translation, and sanitized provider logs.

The shared conformance suite will be installed only as test code from the same
tagged package. Team 2 will supply a controlled service factory and isolated
event data, run applicable GET checks in normal CI, and clean mutable fixtures
between cases. The complete suite will be enabled as create, replace, and delete
are migrated.

Live verification follows [PROVIDER.md](PROVIDER.md): configure OAuth and the
calendar ID, start the service, retrieve a known disposable event through the
HTTP API, compare the four public fields with Google Calendar, test a missing
ID, and remove any disposable data. The recorded response must be sanitized;
tokens, credentials, calendar IDs, and private event IDs are never committed.

## Migration strategy

### Included in this slice

- preserve the joint memo separately from this Team 2 design;
- split routing, HTTP validation, and provider composition out of `main.py`;
- remove hidden `request.state` communication from validators/error rendering;
- avoid repeated validation on the migrated GET HTTP path;
- add sanitized provider-layer operation logging;
- rename ambiguous raw Google helpers;
- rename chronology-based test modules by behavior;
- pin and consume the shared release once an upstream tag exists;
- migrate GET success and failures to shared models/errors;
- run applicable shared conformance checks and live GET verification.

### Follow-up work

Separate owned issues are still required for shared create, replace, and delete;
remaining local-model/error removal; broader behavior-based test grouping; and
any remaining module reorganization. Listing and PATCH stay documented Team 2
extensions. Each issue must identify an owner, a reviewer, its shared-package
dependency, focused checks, and real-provider verification where applicable.

## Alternatives considered

### Depend on a branch or commit temporarily

Rejected. The milestone requires a tagged shared revision, and a moving branch
would make fresh-checkout reproduction unreliable. A commit pin would be
immutable but would not satisfy the explicit tagged-release requirement.

### Copy shared models into this repository

Rejected. Copying would preserve the duplication the shared package is meant to
eliminate and would allow the three services to drift.

### Migrate every operation in one change

Rejected for this checkpoint. It would mix contract adoption with a large
rewrite and make it harder to review whether the first vertical slice has clean
boundaries.

### Add a dependency-injection container or provider registry

Rejected. FastAPI dependencies and ordinary Python parameters already provide
the required composition and test replacement points.

## Open questions and release blockers

1. Which Team 2 teammate and which external Calendar-team member will record
   design approval?
2. Which issue numbers and owners will track each remaining shared operation and
   broader test/module organization?
3. Where will the sanitized live-provider response and exact CI links be
   recorded for submission?

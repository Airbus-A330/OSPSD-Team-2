# Shared Calendar Contract Migration Design

| Metadata | Value |
|---|---|
| Authors | Alexander Freedman and OSPSD Team 2 |
| Team / vertical | Team 2 / Calendar |
| Team reviewer | Pending full-design review |
| Cross-team reviewer | Karthik Ganeshan, Team 7 (contract-facing review comments addressed) |
| Status | In review |
| Last updated | 2026-11-04 |
| Shared revision | [`v0.1.0-rc.1`](https://github.com/Airbus-A330/OSPSD-Calendar/tree/v0.1.0-rc.1), commit `1c1cad7a0732ddb242a05400d8833d94e4422424` |
| Shared HTTP contract | [`docs/HTTP_CONTRACT.md`](https://github.com/Airbus-A330/OSPSD-Calendar/blob/v0.1.0-rc.1/docs/HTTP_CONTRACT.md) |
| Joint decision memo | [Local preserved copy](JOINT_CALENDAR_CONTRACT.md) |
| Implementation | [Migration pull request](https://github.com/Airbus-A330/OSPSD-Team-2/pull/60) |

## Scope and status

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
    -> CalendarService.get  shared Python operation boundary
    -> app/calendar_service.py adapter to existing application operations
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
    -> get_calendar_service wraps the provider as a CalendarService
    -> read_event calls CalendarService.get with the validated ID
    -> CalendarServiceAdapter delegates to application get_event
    -> CachedEventProvider serves a hit or delegates
    -> GoogleCalendarProvider executes events.get
    -> provider response is translated to the domain Event
    -> FastAPI serializes the shared Event response shape
```

The HTTP dependency is the authoritative blank-ID validation point for this
migrated route. The application operation retains optional validation for
non-HTTP callers, while the route explicitly skips the duplicate check after
the dependency has succeeded. Non-HTTP consumers construct
`CalendarServiceAdapter(provider)` with ID validation enabled by default. The
HTTP composition opts out only after the route's early ID validation, retaining
the existing request-scoped client cleanup and cache.

## Shared API and model mapping

The shared release-candidate tag is pinned and locked with uv. The migrated GET
slice uses the shared `Event`, `CalendarError`, and `ErrorCode` at runtime. The
remaining shared models map to later operation migrations:

| Shared package | Team 2 use |
|---|---|
| `Event` | Runtime response and Google translation model, including GET |
| `CreateEvent` | shared POST request fields |
| `ReplaceEvent` | shared PUT request fields |
| `CalendarError` / `ErrorCode` | provider-independent failure boundary |
| `CalendarService` | GET route consumes `get`; adapter bridges the existing four application operations |

Team 2's list limit, `EventPatch`, listing, and PATCH methods remain local
extensions. They must not be added to or presented as requirements of the
shared core. Only GET has migrated its HTTP contract; the adapter's other methods
reuse existing operations and do not claim full write/delete conformance.
Compatibility aliases may be retained briefly if needed to keep a
small migration diff, but validation and models must have one implementation.

## Failure behavior

The shared contract requires `invalid_input`, `not_found`, `access_denied`,
`provider_error`, and `provider_unavailable`, including required `retryable` in
the HTTP error body. HTTP status mapping remains a Team 2 HTTP concern;
provider code raises shared errors rather than returning HTTP responses.

Representative successful request and sanitized response:

```http
GET /events/example-event
```

```json
{
  "id": "example-event",
  "title": "Team sync",
  "start": "2026-11-04T15:00:00Z",
  "end": "2026-11-04T15:30:00Z"
}
```

An untitled provider event returns the same response with `"title": ""`. The
example is synthetic, not a capture from a private calendar. The procedure for
recording a sanitized live response is in [PROVIDER.md](PROVIDER.md).
[The observed GET verification](HW2_MS2_GET_VERIFICATION.md) records a real
HTTP-to-Google success and missing-event run with the shared adapter, including
the tested source revision, redactions, and reproduction steps.

Google HTTP and transport failures are logged before translation using safe
operation context. HTTP logging records the public operation, shared code,
status, and whether the error explicitly indicates provider involvement. No
layer logs credentials, authorization headers, raw payloads, event IDs, or
provider error messages.

| Google/read outcome | HTTP | Shared code | `retryable` |
|---|---:|---|---:|
| Missing event | 404 | `not_found` | `false` |
| Permission denied | 403 | `access_denied` | `false` |
| Invalid or unexpected success payload | 502 | `provider_error` | `false` |
| Quota/rate limit, 5xx, or transport failure on GET | 503 | `provider_unavailable` | `true` |
| Invalid path input | 422 | `invalid_input` | `false` |

Create and replace have a different safety constraint: when a write may have
reached Google but its response is lost, the shared contract requires 502
`provider_error` with `retryable=false`. The existing application does not retry
uncertain writes; adding the shared error envelope to their legacy HTTP routes
remains part of their migration. Resending could duplicate or repeat a change.

## Operational considerations

Google OAuth files remain local and ignored. Each request owns and closes its
Google client because its HTTP transport is not safe to share across worker
threads. The process-local cache continues to share domain `Event` values only;
it does not retain SDK objects. The migration does not change cache TTL,
capacity, invalidation, or concurrency behavior.

### Container and deployment foundation (issue #68)

The local implementation uses one Render **Free** image-backed web service,
one worker, and ephemeral storage, following Alexander's November 9 clarification.
`Dockerfile` uses digest-pinned Python/uv bases and locked application dependencies.
The Blueprint in `infra/render.template.yaml` takes an immutable published image
reference and does not provision a disk or database. See
[DEPLOYMENT.md](DEPLOYMENT.md) for bootstrap, preview/reapply, cost limits and teardown.

The hosted entry point, `app.hosting:app`, validates runtime authorization and
initializes a private disposable token cache on every start without contacting
Google. Render's protected runtime JSON is the source for restart recovery;
operator credential updates replace stale cached state on restart. The service
requires bearer authorization for API traffic and exposes provider-independent
`/healthz` and `/readyz`. Local development retains `app.main:app`. Refresh is
serialized between threads and cached atomically, without interactive login.

Free instances sleep on idle, lose local files across restarts, and have cold-start
latency and usage limits. Credential expiry/revocation requires updating the
runtime secret. The pipeline/smoke tests (#69) and SLO work must account for these
constraints without blindly retrying writes. Calendar data remains in Google.

This is local implementation, not cloud deployment evidence. Account ownership,
platform-aware validation and independent teammate deployment/reapply/API/teardown
verification remain pending. Hobby workspaces allow only one member: the protected,
shared infrastructure-state requirement remains unresolved. Choosing ephemeral
storage does not waive it or authorize a paid workspace. No cloud resources have
been provisioned by #68.

## Testing

Fast tests continue to replace the provider or SDK boundary and require no
credentials or network. The migrated slice needs evidence at four levels:

1. shared-package model and error tests in the shared repository;
2. Team 2 application tests using a controlled service/provider;
3. HTTP tests for exact GET success and shared error responses;
4. Google-adapter tests for SDK calls, translation, and sanitized provider logs.

The service proves the migrated GET behavior with focused model, application,
HTTP, and Google-adapter tests. `tests/test_shared_calendar_service.py` also
reuses the tagged suite's GET success and missing-event cases. It overrides
their fixtures with an isolated controlled Google SDK, so no shared create or
delete is needed to seed or clean up state. The tests exercise the real adapter
through a `CalendarService`-typed consumer; a separate HTTP test substitutes a
shared-only service, which exposes any accidental dependency on local methods.
The complete shared conformance
suite requires create, replace, and delete and is therefore a Milestone 3 task;
it will use the same tagged package, isolated event data, and fixture cleanup.

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
- verify GET with controlled tests and the documented live-provider procedure.

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
3. The [sanitized live-provider response](HW2_MS2_GET_VERIFICATION.md) is recorded.
   Attach the reviewed commit and matching CI links when these changes are pushed.

## Change history

- 2026-11-09: changed #68 to Render Free without a persistent disk; restored OAuth
  cache from runtime configuration on each start and documented cold-start/access limits.

- 2026-11-09: added the issue #68 container/Blueprint foundation, hosted startup
  validation and health/access behavior; recorded pending cloud and teammate checks.

- 2026-11-04: added a proposed deployment approach, tools, and operational
  assumptions in response to Team 5's review; platform selection remains
  pending team confirmation, with implementation planned for Milestone 3.

- 2026-11-04: routed GET through `CalendarService.get`, reused shared GET
  conformance cases with seeded SDK fixtures, and recorded real-provider HTTP
  verification of the adapter working tree.

- 2026-11-04: pinned and locked shared release candidate `v0.1.0-rc.1`.
- 2026-11-04: migrated GET response construction and error semantics to shared
  runtime types; added controlled untitled-event and temporary-outage coverage.
- 2026-11-04: incorporated Team 7 contract-facing review comments concerning
  error codes, `retryable`, 422 validation, temporary failures, untitled events,
  and uncertain writes.

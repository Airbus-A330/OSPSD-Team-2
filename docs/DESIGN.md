# Shared Calendar Contract Migration Design

## Milestone 3 observability

The four shared CRUD operations retain their existing routes, application/cache
behavior, and Google provider semantics. `app/telemetry/` supplies bounded OTLP
metrics/logs/traces through the application factory's lifespan and ASGI middleware.
Google Create/Get/Replace/Delete operations have CLIENT spans including response
translation; PUT's fresh GET preflight is a separate span. Cache hits have no
outbound span. Success requires the operation's exact contract status, and
unexpected 2xx/3xx responses use `unexpected_status` for reliability consumers.
No body, raw identifier, provider payload, or exception text is exported.
Saturation measures occupied AnyIO workers relative to the actual worker limit.
Configuration, golden-signals dashboard, hosted-lifecycle integration, Level 4
schema, and outstanding deployed evidence are canonical in
[OBSERVABILITY.md](OBSERVABILITY.md). Listing and PATCH remain supported extensions.

| Metadata | Value |
|---|---|
| Authors | Alexander Freedman and OSPSD Team 2 |
| Team / vertical | Team 2 / Calendar |
| Team reviewer | Pending full-design review |
| Cross-team reviewer | Karthik Ganeshan, Team 7 (contract-facing review comments addressed) |
| Status | Common operations implemented; live workflow and review pending |
| Last updated | 2026-11-09 |
| Shared revision | [`v0.1.0-rc.1`](https://github.com/Airbus-A330/OSPSD-Calendar/tree/v0.1.0-rc.1), commit `1c1cad7a0732ddb242a05400d8833d94e4422424` |
| Shared HTTP contract | [`docs/HTTP_CONTRACT.md`](https://github.com/Airbus-A330/OSPSD-Calendar/blob/v0.1.0-rc.1/docs/HTTP_CONTRACT.md) |
| Joint decision memo | [Local preserved copy](JOINT_CALENDAR_CONTRACT.md) |
| Implementation | [Migration pull request](https://github.com/Airbus-A330/OSPSD-Team-2/pull/60) |

## Scope and status

This design covers Team 2's four common HW2 operations: POST, GET-one, PUT,
and DELETE. Issue #67 completes the application integration begun with GET-one.
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
2. Route all four common operations through the shared CalendarService interface.
3. Preserve real Google Calendar retrieval and the existing cache behavior.
4. Keep Google SDK objects and configuration behind the provider boundary.
5. Make HTTP routing, request validation, application behavior, composition,
   and provider integration independently understandable.
6. Log safe Google operation and status context where provider failures occur.
7. Pass the complete tagged conformance suite through Python and HTTP.

## Non-goals

This integration does not standardize Team 2's optional listing or PATCH extensions,
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
    -> CalendarService      shared create/get/replace/delete boundary
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

The shared release-candidate tag is pinned and locked with uv. All common
operations consume shared runtime models, errors, and the service interface:

| Shared package | Team 2 use |
|---|---|
| `Event` | All response and provider translation models |
| `CreateEvent` | POST input, passed unchanged through adapter/application/provider |
| `ReplaceEvent` | PUT input, passed unchanged through adapter/application/provider |
| `CalendarError` / `ErrorCode` | Expected failures and common HTTP error rendering |
| `CalendarService` | All four common routes depend on this interface |

`CreateEventRequest` and `EventReplacement` are import aliases for shared models,
not local schemas. The adapter no longer converts between competing models.
Shared validators enforce strict strings, nonblank write titles, RFC 3339 with
explicit offsets, increasing ranges, and rejected unknown fields. The application
adds no title-length limit or fractional-second truncation. HTTP validates before
client setup; non-HTTP callers construct the same validated shared models.
Existing service exception names subclass `CalendarError` for compatibility and
add only local context; they do not define different core codes or retry semantics.

Team 2's list limit and `EventPatch` remain local extensions. Their legacy error
envelopes and validation behavior are retained; they are not requirements of the
shared core. No provider SDK types cross the domain boundary.

POST and PUT parse the shared model before resolving `get_calendar_service`,
then call `create` or `replace`. DELETE validates the ID before calling `delete`.
The adapter delegates to the existing application operations and cached provider.
Google PUT performs its existing uncached preflight so a cancelled/missing event
cannot be revived. The cache invalidates across mutations and uncertain failures.

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

All common routes render the shared envelope, including `retryable`. Malformed,
non-JSON, or empty bodies return 400; valid JSON violating a schema/value rule,
unknown fields, and blank path IDs return 422. Messages are fixed and sanitized.

Confirmed Google quota refusals (429 or 403 with a limit reason) become 503
`provider_unavailable`, including on writes. Setup/preflight failures before a
mutation can also be safely classified as unavailable. Write transport failures,
5xx, and invalid success payloads instead use 502 `provider_error` with
`retryable=false`: the mutation may have taken effect. Reads map temporary 5xx
and transport failures to unavailable. No operation automatically retries.
DELETE retains 404 for absence and Google's explicit 410 `deleted` response.

## Operational considerations

Google OAuth files remain local and ignored. Each request owns and closes its
Google client because its HTTP transport is not safe to share across worker
threads. The process-local cache continues to share domain `Event` values only;
it does not retain SDK objects. The migration does not change cache TTL,
capacity, invalidation, or concurrency behavior.

### Proposed deployment (pending team review)

This proposal addresses HW2 section 4.6; it is not an approved platform choice
or evidence of deployment. We propose one paid Render web service running a
Docker image with one Uvicorn worker. The assumption is low-volume classroom
use, with brief deployment downtime acceptable. Google remains the event store;
the existing cache stays disposable and process-local. Render's
[persistent-disk limits](https://render.com/docs/disks) rule out multiple
instances and zero-downtime deployment for this proposal.

Use a versioned `render.yaml` [Blueprint](https://render.com/docs/blueprint-spec)
to declare the service, disk, and configuration placeholders. GitHub Actions
would run the required checks, build the locked-dependency Docker image once,
and publish it to GitHub Container Registry. The deployment workflow would
deploy that [prebuilt image by digest](https://render.com/docs/deploying-an-image),
run a shared-API smoke check with cleanup, and retain the previous digest for
rollback. Validate infrastructure previews and repeatable application before
accepting this approach for Milestone 3.

Supply OAuth client configuration and initial authorization through
[runtime secret files](https://render.com/docs/configure-environment-variables),
never through Git or the image. Seed the token onto a private writable disk
only when absent, using `GOOGLE_CALENDAR_TOKEN_FILE` for its path. Before hosting,
replace browser-based authorization fallback with a sanitized setup failure,
serialize credential refresh and persist tokens atomically. One worker still
serves concurrent requests, so it does not remove that synchronization need.
Restrict access to the hosted write API to authorized reviewers.

Before provisioning, the team must confirm account access, an account/billing
owner, current compute/disk/registry costs, a spending cap, and a teardown date.
No free-tier or budget assumption is approved. Revisit the platform if cost,
credential persistence, or required infrastructure checks cannot be supported.
Provisioning, health checks, deployment/rollback, telemetry, and teardown
verification remain November 11 Milestone 3 work; no resources have been created.

## Testing

Fast tests control provider or SDK boundaries and require no credentials or
network. `tests/integration/test_shared_conformance.py` inherits the entire tagged
`CalendarServiceConformance`, running against the production adapter/cache/Google
integration both directly and through HTTP. A stateful SDK fixture models remote
records and deleted tombstones; upstream fixtures create and clean up isolated
data. Failure injection occurs at SDK calls, including after a mutation, so tests
exercise actual Team 2 translation rather than injecting pretranslated errors.

`tests/integration/test_shared_http.py` tests the 400/422 distinction, strict
shared values, unknown fields, unchanged accepted strings, and safe error bodies.
Shared-only substitutes prove that all four routes depend on `CalendarService`.
Existing tests retain listing/PATCH and cache coverage. The existing `make test`
and Tests CI collect the entire suite without workflow changes.

The opt-in `tests/live/test_shared_workflow.py` exercises real POST → GET → PUT →
GET → DELETE, then repeated DELETE, missing GET and missing PUT. Reads bypass
cache expiration, and cleanup runs in `finally`. No live verification was possible
in this environment on 2026-11-09; the user confirmed a teammate will run it with
credentials. [PROVIDER.md](PROVIDER.md#hw2-shared-workflow-verification) documents
setup, the exact command, cleanup limits for uncertain creation, and evidence
still required. Earlier GET-only evidence is not proof of this workflow.

## Migration strategy

### Milestone 2 foundation (completed)

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

### Milestone 3 integration completion

Issue #67 completes shared create/replace/delete model and HTTP adoption and
full controlled conformance. Compatibility import aliases keep the diff focused;
shared models and validators remain the sole implementation for core writes.
Listing/PATCH remain supported local extensions.

### Follow-up work

A credential-owning teammate must run and record the live workflow and cleanup.
Review and CI on the submitted revision are still required. Infrastructure,
deployment, telemetry, reliability, and broader module reorganization belong to
separate issues; their proposed deployment section above is intentionally unchanged.

## Alternatives considered

### Depend on a branch or commit temporarily

Rejected. The milestone requires a tagged shared revision, and a moving branch
would make fresh-checkout reproduction unreliable. A commit pin would be
immutable but would not satisfy the explicit tagged-release requirement.

### Copy shared models into this repository

Rejected. Copying would preserve the duplication the shared package is meant to
eliminate and would allow the three services to drift.

### Migrate every operation in one change

Deferred at the Milestone 2 checkpoint to establish one clean vertical slice.
Issue #67 now completes the common operations using that existing architecture,
without rewriting the service or changing extension behavior.

### Add a dependency-injection container or provider registry

Rejected. FastAPI dependencies and ordinary Python parameters already provide
the required composition and test replacement points.

## Open questions and release blockers

1. Which Team 2 teammate and which external Calendar-team member will record
   design approval?
2. Which credential-owning teammate will record the full shared live workflow
   and cleanup for issue #67? Broader test/module reorganization stays separate.
3. The [sanitized live-provider response](HW2_MS2_GET_VERIFICATION.md) is recorded.
   Attach the reviewed commit and matching CI links when these changes are pushed.

## Change history

- 2026-11-09: issue #67 routes all common operations through `CalendarService`,
  aliases shared write models, adopts shared HTTP errors and validation, and
  runs complete controlled conformance through Python and HTTP. Live workflow
  verification remains pending credentials and a teammate; no deployment work
  is included.

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

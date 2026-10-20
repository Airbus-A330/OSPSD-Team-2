# Public Contract

This document is the canonical source of truth for the service's public behavior.

Code, tests, examples, and other documentation must remain consistent with this contract.

Do not change a public contract as a side effect of implementation. Contract changes must be intentional, documented, tested, and reviewed.

---

## Contract Principles

The public API describes the domain of this service, not the representation used by an external provider.

Callers should not need to understand:

- provider SDK types;
- provider-specific request objects;
- provider-specific response objects;
- authentication implementation details;
- unnecessary provider metadata.

Provider-specific data must be translated into the service's public models before it reaches callers.

---

## HTTP API

### Retrieve Event

**Purpose**

Retrieve one titled, timed event from the calendar configured for this service.

**Method**

```text
GET
```

**Route**

```text
/events/{event_id}
```

**Path parameters**

| Name | Type | Required | Meaning |
|---|---|---:|---|
| `event_id` | `string` | yes | Opaque, service-visible identifier of the event to retrieve |

**Query parameters**

None.

**Request body**

None.

**Successful response**

```json
{
  "id": "event-123",
  "title": "Team Meeting",
  "start": "2026-10-01T10:00:00-04:00",
  "end": "2026-10-01T11:00:00-04:00"
}
```

**Success status**

```text
200 OK
```

**Observable behavior**

- A successful request returns the event identified by `event_id` as an `Event`.
- The response `id` matches the requested `event_id`.
- The response contains exactly the public Event fields documented below.
- Provider-specific metadata is not exposed.
- Callers must not rely on the example field values shown above.

**State changes**

This operation reads event state and does not create, modify, or delete an event.

**Caching**

Successful event reads are cached in memory for 60 seconds using the configured
calendar ID and requested event ID as the cache key. A repeated request may
therefore return data that is up to approximately 60 seconds older than the
provider's current value. After expiry, the next request retrieves and caches a
fresh provider result. Invalid input and failed retrievals are not cached.

The cache is local to one running service process and is cleared when that
process stops. If write operations are added later, they must invalidate or
update affected entries; the current service is read-only.

**Errors**

The team-approved Level 5 contract uses service exceptions from `app.errors`.
All four categories inherit from `ServiceError` and use normal `Exception`
construction, such as `InvalidInputError("internal context")`. Exception messages
are internal/debugging context only; HTTP responses must use the fixed public
messages below, never arbitrary exception text or Google error messages.

| Service exception | When it occurs | Code | HTTP status | Public message | Retry |
|---|---|---|---:|---|---|
| `InvalidInputError` | Event ID is empty or whitespace-only | `invalid_input` | 400 | `Invalid event ID` | No, unless the caller changes the input |
| `NotFoundError` | Requested event does not exist | `not_found` | 404 | `Event not found` | No, unless the identifier/resource changes |
| `PermissionDeniedError` | Access to the event is denied | `permission_denied` | 403 | `Permission denied` | No, unless access/authorization changes |
| `ProviderFailureError` | Provider failure prevents retrieval | `provider_error` | 502 | `Calendar provider request failed` | Potentially, depending on the underlying failure |

Public error responses have exactly this shape:

```json
{
  "error": {
    "code": "invalid_input",
    "message": "Invalid event ID"
  }
}
```

Local validation rejects empty and whitespace-only strings before invoking
`EventProvider.get_event`. Every other string is passed unchanged, including
leading/trailing whitespace and unusual characters. There is no local Google
event-ID syntax validation or trimming. Existence and provider-specific validity
remain the provider's responsibility.

`/events` and `/events/` without an ID remain ordinary unmatched-route 404s,
not Level 5 `invalid_input` errors.

Implementation status: service exceptions, application-level validation, HTTP
rendering of the four shared exceptions, and sanitized failure logging are
implemented. HTTP validation runs before provider setup; the application operation
also validates non-HTTP calls. Controlled-provider tests verify these responses.
Google-specific failure translation is implemented in the Google provider
(#38). Live-provider failure behavior has not been verified.

---

## Domain Models

Public domain models belong here.

For each model, document:

- field name;
- type;
- whether it is required;
- meaning;
- important invariants.

### Event

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | `string` | yes | Service-visible event identifier |
| `title` | `string` | yes | Human-readable event title |
| `start` | `string` | yes | Inclusive start date and time for a timed event |
| `end` | `string` | yes | Exclusive end date and time for a timed event |

All four fields are required strings. `start` and `end` preserve their source
date-time strings without timezone conversion or normalization. The current
contract supports titled, timed events only; all-day events are not supported.

---

## Contract Change Rules

A public contract change requires:

1. an intentional decision by the team;
2. updated contract documentation;
3. updated implementation;
4. updated unit or contract tests;
5. updated integration tests where applicable;
6. an explicit note in the pull request.

Do not modify the public API merely to match an external provider's representation.

---

## Assumptions

- The service operates on one configured calendar. Calendar selection is not a
  caller-provided parameter in Milestone 1. Revisit this if callers need access
  to more than one calendar.
- Event identifiers are opaque strings and must not be parsed by callers. Revisit
  this only if the service introduces its own identifier scheme.
- Only titled, timed events are supported. Revisit the Event model before adding
  all-day or untitled events.
- Date-time strings are not normalized in Milestone 1. Revisit their exact format
  before callers need date-time comparison or conversion guarantees.
- The Level 5 error contract above is frozen; provider translation and HTTP
  integration must implement it without exposing provider-specific details.

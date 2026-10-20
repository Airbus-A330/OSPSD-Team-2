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

`GET /events` is the listing operation below. `GET /events/` redirects to
`/events`; neither is a missing-ID `invalid_input` error.

Implementation status: service exceptions, application-level validation, HTTP
rendering of the four shared exceptions, and sanitized failure logging are
implemented. HTTP validation runs before provider setup; the application operation
also validates non-HTTP calls. Controlled-provider tests verify these responses.
Google-specific failure translation is implemented in the Google provider
(#38). Live-provider failure behavior has not been verified.

---

### List Events

**Owner:** Maksym Yemelianenko (#51, Operation 2).

`GET /events` reads a small collection from the configured calendar. It accepts
one optional integer query parameter, `limit`: default **10**, minimum **1**,
maximum **100**. There is no request body. Invalid limits are rejected before
provider setup or retrieval with HTTP 400:

```json
{"error": {"code": "invalid_input", "message": "Invalid event limit"}}
```

Success is HTTP **200** with a JSON array of zero to `limit` public `Event`
objects, each containing exactly `id`, `title`, `start`, and `end`. Timestamp
strings retain their provider offsets. IDs can be used with GET-one. The
operation is read-only and safe to repeat; separate requests are not a snapshot.

This first version returns one provider page in provider order. It does not
promise chronological order, a full calendar traversal, or a full page. No Google
page tokens or collection metadata are exposed. Only titled, timed events are
supported, as for GET-one; an unsupported event in the page produces the shared
502 `provider_error` response instead of silently dropping it or inventing fields.

Other provider failures reuse the existing shared response shape and status/code
mapping above (403 permission denial, 404 provider-reported missing resource, 502
provider failure). Retry advice remains the same; this service does not retry
requests automatically. Locally rejected limits cause no provider work.

With provider setup complete, run:

```bash
curl -i 'http://127.0.0.1:8000/events?limit=2'
```

Expected: 200 and an array such as `[{"id":"event-123","title":"Team Meeting",
"start":"2026-10-01T10:00:00-04:00","end":"2026-10-01T11:00:00-04:00"}]`,
or `[]` if the page has no events. No calendar state changes or cleanup are needed.
See [PROVIDER.md](PROVIDER.md#list-events-verification) for live verification.

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

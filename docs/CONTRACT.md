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

No service-specific missing-event or provider-error response is guaranteed in
Milestone 1. Those behaviors must be defined before they become part of the
public contract.

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
- Missing-event and provider-failure behavior is intentionally unspecified until
  the service implements and tests those cases consistently.

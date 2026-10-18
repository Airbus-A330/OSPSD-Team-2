# Architecture

This document describes the intended structure and dependency boundaries of the service.

Keep this document synchronized with meaningful architectural changes.

The architecture should remain as small as possible while preserving clear responsibilities.

---

## Design Goals

The codebase should optimize for:

1. correctness;
2. readability;
3. clear public contracts;
4. testability;
5. simple dependency direction;
6. easy contribution by another developer.

Avoid architecture whose complexity exceeds the problem it solves.

---

## System Boundary

At a high level:

```text
Caller
  ↓
FastAPI HTTP API
  ↓
Application / domain behavior
  ↓
Provider boundary
  ↓
Provider-specific implementation
  ↓
External provider
```

Responses travel back through the same layers:

```text
External provider
  ↓
Provider-specific translation
  ↓
Domain representation
  ↓
FastAPI response
  ↓
Caller
```

Provider SDK objects should not become public API objects.

---

## Responsibilities

### HTTP Layer

Responsible for:

- HTTP request parsing;
- path/query/body validation;
- invoking application behavior;
- HTTP response serialization;
- HTTP status codes.

Should remain thin.

Should not contain substantial provider-specific logic.

---

### Application / Domain Layer

Responsible for:

- service-level behavior;
- domain decisions;
- coordinating operations;
- working with provider-independent domain data where applicable.

Application logic should not depend unnecessarily on HTTP concepts.

---

### Models

Responsible for:

- explicit data shapes;
- public request and response models;
- important domain invariants.

Use Pydantic at API/configuration boundaries.

Use simpler Python types or dataclasses internally when they communicate the model more clearly.

---

### Provider Integration

Responsible for:

- provider authentication;
- provider SDK/API calls;
- provider-specific identifiers where necessary;
- translating provider-specific representations into service-domain representations;
- translating provider failures at the appropriate boundary.

Provider SDK-specific types should remain localized here.

---

### Configuration

Responsible for:

- environment-based configuration;
- provider configuration;
- credential locations or references.

Secrets must never be hardcoded or committed.

---

## Dependency Direction

Prefer dependencies that point inward toward service/domain concepts.

Conceptually:

```text
HTTP
 ↓
Application
 ↓
Domain contract
 ↑
Provider implementation
```

External provider details should not spread throughout the application.

Avoid circular dependencies.

---

## Code Organization

Do not create directories merely to satisfy this diagram.

Create modules when actual behavior justifies them.

A possible structure is:

```text
app/
├── main.py
├── models/
├── routes/
├── services/
└── providers/
```

The exact structure may evolve.

Prefer a few coherent files over many trivial modules.

---

## Request Flow

For every public operation, a contributor should be able to trace:

```text
HTTP input
    ↓
validation/parsing
    ↓
application decision
    ↓
provider interaction, if required
    ↓
provider → domain translation
    ↓
public response construction
```

Document unusual deviations.

---

## External Boundaries

External dependencies should have clear boundaries because they are:

- slower than local code;
- capable of failing independently;
- difficult to reproduce deterministically;
- often provider-specific.

Tests should normally control these boundaries using fakes, fixtures, or mocks.

Real-provider verification is separate.

---

## Milestone 2 Provider Boundary

Milestone 2 uses this provider-independent contract:

```python
class EventProvider(Protocol):
    def get_event(self, event_id: str) -> Event: ...
```

`get_event` retrieves one event by its service-visible identifier. The
`event_id` input is an opaque string supplied by the caller, and the return
value is the existing service-domain `Event` model. The operation is read-only:
it does not create, update, or delete provider state. Callers may depend on
these properties, but not on Google identifiers, request shapes, response
objects, or SDK types.

Normal execution follows this dependency direction:

```text
FastAPI route
    ↓
application get_event operation
    ↓
EventProvider
    ↓
GoogleCalendarProvider
    ↓
Google Calendar SDK/API
```

Tests replace the provider at the same boundary:

```text
test
    ↓
application get_event operation
    ↓
EventProvider
    ↓
ControlledEventProvider
```

Application code depends only on `EventProvider` and domain models, while HTTP
code remains provider-independent. Google SDK calls, request construction,
response parsing and translation, and Google-specific configuration remain
inside the concrete Google provider. Neither raw provider dictionaries nor
Google SDK objects cross the interface. Startup or other composition code
selects and supplies the concrete provider; application logic must not import or
construct it.

This is the frozen target boundary for Levels 3–4, not a claim that the current
implementation already satisfies those levels. It intentionally contains only
the `get_event` operation needed now and does not imply support for multiple
real providers or runtime provider switching. Implementing it must preserve the
existing `GET /events/{event_id}` public contract in `CONTRACT.md`.

---

## Architectural Changes

Before introducing a new:

- abstraction;
- service layer;
- factory;
- interface;
- dependency;
- queue;
- cache;
- database;
- worker;
- package;

answer:

1. What concrete problem does it solve?
2. Why is the current simpler structure insufficient?
3. What additional complexity does it introduce?
4. How will it be tested?
5. Can the same goal be achieved more simply?

Do not add architectural machinery based only on anticipated future needs.

---

## Current Code Map

The provider-independent contract, application operation, Google provider, and
FastAPI composition are implemented as described above.

| Module | Current Responsibility |
|---|---|
| `app/main.py` | FastAPI entry point and composition of the configured Google provider |
| `app/http_errors.py` | Fixed HTTP responses for shared service exceptions and sanitized failure logging |
| `app/events.py` | Provider-independent application operation for retrieving an event |
| `app/errors.py` | Provider-independent service exceptions defined by the Level 5 contract in `CONTRACT.md` |
| `app/providers.py` | Provider-independent `EventProvider` protocol |
| `app/models.py` | Public `Event` domain model |
| `app/google_calendar.py` | Google authentication, client construction, retrieval, translation, and concrete `GoogleCalendarProvider` |

Do not describe files here before they exist.

## Level 5 HTTP Failure Boundary

FastAPI registers handlers for the four service exceptions from `app.errors`.
`app/http_errors.py` maps them to the exact public responses in
[CONTRACT.md](CONTRACT.md); it neither inspects Google exceptions nor returns
exception text. Other exceptions remain distinguishable from expected failures.

The route runs shared `app.events.validate_event_id` validation before resolving
the provider dependency. The application operation also uses this validator for
non-HTTP callers. This preserves #37's rule without duplicating it: blank IDs
fail locally, and every other identifier passes through unchanged.

Failure logs contain operation, service error code, HTTP status, and request-local
`provider_involved` context. This flag means provider setup or retrieval was
attempted, not that a remote call completed. It is false for locally rejected
input and true when composition or retrieval begins; unavailable context is
recorded as unknown. Logs exclude exception text, request headers, event IDs,
provider payloads, and expected-failure tracebacks.

The Google client remains request-scoped and is closed in the composition
dependency's `finally`, including when retrieval raises a handled service error.

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

Update this section as implementation is added.

| Module | Responsibility |
|---|---|
| `app/main.py` | Application/FastAPI entry point |
| `app/google_calendar.py` | Retrieve raw Google event data using a supplied Calendar client; translation is required before HTTP use |

Do not describe files here before they exist.

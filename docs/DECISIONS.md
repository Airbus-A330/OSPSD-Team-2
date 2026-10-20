# Technical Decisions

Record only decisions significant enough that a future contributor might reasonably ask, "Why did we do it this way?"

---

## 2026-10-11 — Use a minimal provider interface for event retrieval

**Context**

Level 3 requires a provider-independent boundary, and Level 4 requires that
tests can replace the concrete provider. The service currently needs only one
provider-backed behavior: retrieving one event.

**Decision**

Use `EventProvider` with `get_event(event_id: str) -> Event`. Keep Google SDK
calls, request construction, response translation, and Google-specific
configuration behind the concrete provider implementation. Supply that
implementation to application logic instead of constructing it there.

**Alternatives**

- Expose the Google SDK directly to application code.
- Mirror more of the Google Calendar API in a larger abstraction.
- Introduce a dependency-injection framework.
- Create a larger abstract-class hierarchy.

**Why**

This satisfies the current requirements while keeping the boundary explicit,
small, domain-oriented, and testable.

**Trade-offs**

The interface supports only the one behavior currently required. Future
operations may require deliberate extension.

**Revisit when**

A required operation cannot be expressed cleanly through this interface, or a
second real provider reveals a genuine incompatibility.

**Revisited 2026-10-20**

The final API requires six public calendar operations. The interface now contains
only their provider-independent signatures: retrieve, list, create, replace,
partial update, and delete. Request models describe service-domain values, and
all returned events use the same four-field `Event` model. The team retained this
single small protocol and ordinary FastAPI dependency replacement instead of
introducing a broader provider abstraction, provider registry, or dependency-
injection framework.

---

## Decision Template

### YYYY-MM-DD — Decision title

**Context**

What problem required a decision?

**Decision**

What did we choose?

**Alternatives**

What reasonable alternatives were considered?

**Why**

Why was this option selected?

**Trade-offs**

What do we gain and give up?

**Revisit when**

What evidence or requirement would cause us to reconsider?

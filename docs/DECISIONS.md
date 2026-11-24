# Technical Decisions

Record only decisions significant enough that a future contributor might reasonably ask, "Why did we do it this way?"

---

## 2026-11-23 — Separate model judgment from deterministic execution

**Context**

HW3 requires natural-language planning while preserving the existing API's
validation, provider, and failure boundaries. Model output is nondeterministic
and retrieved provider content may be adversarial, so neither can be an
authorization or execution boundary.

**Decision**

Run the model/tool loop in a separate `agent_service`. Give it a small explicit
registry containing an API-backed read and a multi-vertical proposal tool. A
write-capable request produces an exact digest-bound proposal and stops at
`approval_required`; this issue exposes no write execution tool. Code validates
schemas, limits, cancellation, persistence, and tool policy.

**Alternatives**

- Embed the language model in the API service.
- Let the model call provider packages directly.
- Expose each provider endpoint as a separate tool.
- Treat conversational confirmation as write approval.
- Add a general agent or dependency-injection framework.

**Why**

This is the smallest inspectable design that keeps model judgment useful without
moving deterministic application behavior or security policy into a prompt. It
also permits deterministic CI through the same `ModelClient` contract used by
the real model adapter.

**Trade-offs**

Deployment now has two processes, and proposal execution remains unavailable
until authenticated exact-proposal approval is integrated. The development
SQLite store proves restart persistence but is not the final shared multi-user
database.

**Revisit when**

The identity/approval/database work supplies its authenticated execution seam,
or measured real-model evaluation shows that the prompt or product-specific tool
set needs a narrowly scoped change.

---

## 2026-10-11 — Use a minimal provider-independent calendar interface

**Context**

The application needs calendar behavior without coupling HTTP or domain logic to
Google SDK objects, request formats, authentication, or response dictionaries.
Tests must also replace the real provider without credentials or network access.

**Decision**

Use one small `EventProvider` protocol containing only the six public calendar
operations. Keep Google SDK calls, request construction, response translation,
and Google-specific configuration behind the concrete provider implementation.
Supply that implementation to application logic instead of constructing it there.

**Alternatives**

- Expose the Google SDK directly to application code.
- Mirror more of the Google Calendar API in a larger abstraction.
- Introduce a dependency-injection framework.
- Create a larger abstract-class hierarchy.

**Why**

This keeps the boundary explicit, small, domain-oriented, and testable while
supporting every current public operation.

**Evidence**

Controlled substitution tests exercise application and HTTP behavior through
`EventProvider` without Google credentials or network access. Provider tests
verify Google request construction and translation at the SDK boundary. All six
public operations were also verified against Google Calendar on 2026-10-20, and
every returned event uses the same provider-independent `Event` representation.

**Trade-offs**

The interface must be extended deliberately when the public API adds behavior.
It avoids speculative provider features, but a future provider may expose
semantics that require additional normalization.

**Remaining uncertainty**

Only Google Calendar has been implemented. Provider independence is demonstrated
through controlled substitutes, but a second production provider has not yet
shown whether all six operations map cleanly to the current domain types.

**Revisit when**

A required operation cannot be expressed cleanly through this interface, or a
second real provider requires materially different semantics that cannot be
normalized through the current domain types.

**Revisited 2026-10-20**

The API expanded to six public calendar operations. Request models describe
service-domain values, and all returned events use the same four-field `Event`
model. The team retained this single small protocol and ordinary FastAPI
dependency replacement instead of introducing a broader provider abstraction,
provider registry, or dependency-injection framework.

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

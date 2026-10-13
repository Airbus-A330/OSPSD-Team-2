# Testing Strategy

This document records what the project tests and why.

Repository-wide testing rules are defined in `../AGENTS.md`.

## Test Layers

### Unit
Small, deterministic tests of individual behavior.

### Integration
Tests of meaningful boundaries between multiple components.

### Real Provider / E2E
Verification against the actual provider.

## Provider Substitution

For Level 4, fast application tests must replace the real provider at the
`EventProvider` boundary. These tests must require neither Google credentials
nor live network access. Patching only the Google SDK network call does not
demonstrate that application logic can accept a substitute for the provider
interface.

A controlled provider should implement only the behavior required by its tests;
it is not intended to simulate Google Calendar. Real-provider verification
remains separate from the fast automated suite.

## Google Provider Tests

`tests/test_google_calendar_provider.py` tests the concrete
`GoogleCalendarProvider` with a controlled SDK client. Its four cases cover:

- Two calendar/event ID pairs: construction makes no SDK calls, retrieval uses
  the supplied identifiers, and the result is an `Event` with exactly the four
  public fields and unchanged timestamp strings.
- A Google HTTP error: the original exception propagates to the caller.
- An unsupported all-day response: translation raises `KeyError` instead of
  returning raw Google data or inventing timestamps.

These tests run without credentials or network access. Existing mapping and
model tests cover additional missing-field and invalid-type cases. The separate
HTTP integration test covers controlled provider substitution; live Google
connectivity is documented in `PROVIDER.md`.

## CI

Required GitHub Actions checks:

- Build
- Format
- Tests

Normal CI must not require provider credentials.

## Feature Test Matrix

| Feature / Contract | Unit | Integration | Real Provider | Known Gaps |
|---|---:|---:|---:|---|
| Public Event model | Yes | | | `tests/test_event_model.py` covers construction, serialization, required string fields, and timestamp preservation |
| Google Calendar client construction | Yes | | Manual | Automated tests mock OAuth and API client construction |
| FastAPI event endpoint | | Yes | Manual | `tests/test_event_routes.py` overrides `get_event_provider` with a controlled provider and verifies the exact four-field response; live verification is documented in `PROVIDER.md` |
| Provider composition | Yes | | | `tests/test_event_routes.py` verifies configured and default calendar IDs with a controlled SDK client |
| Google event translation | Yes | | | Synthetic timed-event fixtures; all-day and sparse responses are unsupported |
| Google event retrieval | Yes | Yes | Manual | Provider errors remain unspecified; live verification requires team credentials |
| `EventProvider` contract | | Yes | | `app/providers.py` defines the provider-independent `get_event(event_id) -> Event` protocol used by application and Google provider code |
| Google provider implementation | Yes | | Manual | Provider unit tests use a controlled SDK client; live timed-event retrieval is documented in `PROVIDER.md` |
| Application event retrieval through `EventProvider` | | Yes | | `app/events.py` receives a provider and calls its `get_event` operation |
| Controlled provider substitution | | Yes | No | HTTP integration test uses `app.dependency_overrides`; requires no credentials, network access, or Google SDK patching |

Update this table whenever meaningful behavior is added.

Event route tests also cover `/events` and `/events/` without the required ID.
Their 404 responses reflect unmatched routes, not a lookup for a nonexistent event.

## Commands

Run the complete local verification suite from the repository root:

```bash
make check
```

Real-provider authentication and end-to-end verification are documented in
`PROVIDER.md`.

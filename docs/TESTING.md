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

`tests/test_provider_substitution.py` defines `ControlledEventProvider`, a small
mapping from requested identifiers to configured `Event` instances. Its fixture
returns `EventProvider`, so mypy checks structural compatibility with the frozen
interface without requiring inheritance or Google SDK types.

Application tests pass the controlled provider to `app.events.get_event` and
verify two distinct identifiers and repeated reads without state changes. HTTP
tests override `app.main.get_event_provider`, the same FastAPI dependency used
by normal execution, and verify the complete response and unchanged timestamps.
Pytest's `monkeypatch` restores the dependency override after each test, including
on failure. The tests patch neither application behavior nor Google SDK calls.

The fixture creates fresh events per test and can be configured with any required
identifier-to-Event mapping. It contains no authentication, network access, or
Google behavior simulation. Only configured identifiers are used; incidental
missing-key behavior is not a promised application error contract. Real-provider
verification remains separate and documented in [PROVIDER.md](PROVIDER.md).

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
| Service error types | Yes | | | `tests/test_errors.py` verifies exception construction and catching through `ServiceError`; provider translation and HTTP rendering remain separate |
| Local event-ID validation | Yes | | | `tests/test_provider_substitution.py` verifies blank IDs never invoke the provider and nonblank IDs pass unchanged, including whitespace and unusual characters |
| Google Calendar client construction | Yes | | Manual | Automated tests mock OAuth and API client construction |
| FastAPI event endpoint | | Yes | Manual | `tests/test_provider_substitution.py` overrides `get_event_provider` with a controlled provider and verifies the exact four-field response; live verification is documented in `PROVIDER.md` |
| Provider composition | Yes | | | `tests/test_event_routes.py` verifies configured and default calendar IDs with a controlled SDK client |
| Google event translation | Yes | | | Synthetic timed-event fixtures; all-day and sparse responses are unsupported |
| Google event retrieval | Yes | Yes | Manual | Provider errors remain unspecified; live verification requires team credentials |
| `EventProvider` contract | Yes | Yes | | `tests/test_event_provider.py` verifies structural compatibility and domain input/output; the HTTP test verifies substitution through `app/providers.py` |
| Google provider implementation | Yes | | Manual | Provider unit tests use a controlled SDK client; live timed-event retrieval is documented in `PROVIDER.md` |
| Application event retrieval through `EventProvider` | Yes | Yes | | Controlled events verify identifier selection, response preservation, and repeated reads |
| Controlled provider substitution | Yes | Yes | No | `tests/test_provider_substitution.py` uses a configurable provider through application arguments and `app.dependency_overrides` |

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

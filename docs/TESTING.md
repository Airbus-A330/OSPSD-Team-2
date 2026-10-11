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
| FastAPI event endpoint | | Yes | Manual | Default tests control the SDK boundary; live verification is documented in `PROVIDER.md` |
| Google event translation | Yes | | | Synthetic timed-event fixtures; all-day and sparse responses are unsupported |
| Google event retrieval | Yes | Yes | Manual | Provider errors remain unspecified; live verification requires team credentials |
| `EventProvider` contract | Planned | | | Required for Milestone 2; verify its domain input and `Event` output without Google SDK types |
| Google provider implementation | Planned | Planned | Planned | Must implement `EventProvider` and keep Google-specific behavior behind the boundary |
| Application event retrieval through `EventProvider` | | Planned | | Must receive the provider rather than construct or import the Google implementation |
| Controlled provider substitution | | Planned | No | Must exercise application behavior without credentials, network access, or Google SDK patching |

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

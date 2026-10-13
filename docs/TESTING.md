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

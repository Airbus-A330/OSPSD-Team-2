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
| Google Calendar client construction | Yes | | Manual | Automated tests mock OAuth and API client construction |
| FastAPI event endpoint | | Yes | No | Uses stub data; endpoint contract not yet confirmed |
| Google event translation | Yes | | | Synthetic timed-event fixtures; all-day and sparse responses are unsupported |

Update this table whenever meaningful behavior is added.

## Commands

Run the complete local verification suite from the repository root:

```bash
make check
```

Real-provider authentication verification is documented in `PROVIDER.md`.

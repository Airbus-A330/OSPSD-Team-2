# OSPSD Team 2 — Calendar Service

Backend Calendar service developed for NYU's **Open Source and Professional Software Development** course, Fall 2026.

The service exposes a small, provider-independent HTTP API using **Python 3.12** and **FastAPI**, with **Google Calendar** as the concrete provider.

The repository is designed so that another developer can clone it, install dependencies, run the automated checks, start the service, and understand the provider setup without help from the team.

---

## Team Members and Operation Ownership

| Team Member | Public Operation |
|---|---|
| Dorien Zhang | `GET /events/{event_id}` — retrieve an event |
| Maksym Yemelianenko | `GET /events` — list events |
| Alexander Freedman | `POST /events` — create an event |
| Nicolas Ollivier | `PUT /events/{event_id}` — replace an event |
| Yasmin Hassoobh | `PATCH /events/{event_id}` — partially update an event |
| Xingjian Liu | `DELETE /events/{event_id}` — delete an event |

Each operation is implemented through the shared provider-independent `EventProvider` boundary and integrated into the same Calendar service.

---

# Quick Start

## Requirements

- **Python 3.12**
- **uv 0.12.17 or newer**
- Git

Google credentials are **not required** to install the project, run the automated test suite, or start the FastAPI application.

Google OAuth credentials are required only when making requests that use the real Google Calendar provider.

---

## 1. Clone the Repository

```bash
git clone https://github.com/Airbus-A330/OSPSD-Team-2.git
cd OSPSD-Team-2
```

To reproduce a particular submitted release, check out its published tag before installing dependencies:

```bash
git checkout <release-tag>
```

Published release tags are immutable.

---

## 2. Install uv

Check whether uv is already installed:

```bash
uv --version
```

The project supports **uv 0.12.17 or newer**.

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows PowerShell

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Other installation methods are available in the official uv documentation:

https://docs.astral.sh/uv/getting-started/installation/

---

## 3. Install Python and Locked Dependencies

From the repository root:

```bash
uv python install 3.12
uv sync --locked
```

The project uses:

- `pyproject.toml` for direct dependencies;
- `uv.lock` for the exact resolved dependency set.

No virtual-environment activation is required. Use `uv run --locked` for project commands.

---

# Fresh Checkout Verification

A new contributor can verify the repository without Google credentials.

If GNU Make is installed:

```bash
uv sync --locked
make check
```

`make check` verifies:

- formatting;
- linting;
- static type checking;
- automated tests;
- Python compilation;
- application import.

If GNU Make is not available, run the equivalent commands:

```bash
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy .
uv run --locked python -m pytest
uv run --locked python -m compileall app
uv run --locked python -c "import app.main"
```

These automated checks use controlled dependencies and do not require Google credentials or live Google Calendar access.

---

# Running the Service

Start FastAPI from the repository root:

```bash
uv run --locked uvicorn app.main:app --reload
```

The service is available at:

```text
http://127.0.0.1:8000
```

FastAPI Swagger UI is available at:

```text
http://127.0.0.1:8000/docs
```

The canonical API contract is:

[`docs/CONTRACT.md`](docs/CONTRACT.md)

---

# Public API

The final API exposes six operations:

| Method | Route | Behavior |
|---|---|---|
| `GET` | `/events/{event_id}` | Retrieve one event |
| `GET` | `/events` | List events |
| `POST` | `/events` | Create an event |
| `PUT` | `/events/{event_id}` | Fully replace an existing event |
| `PATCH` | `/events/{event_id}` | Partially update an existing event |
| `DELETE` | `/events/{event_id}` | Delete an event |

The public Event representation is:

```json
{
  "id": "event-id",
  "title": "Event title",
  "start": "2026-10-22T10:00:00-04:00",
  "end": "2026-10-22T11:00:00-04:00"
}
```

The service intentionally supports the documented titled, timed-event representation only.

For exact request rules, status codes, validation behavior, and error responses, use:

[`docs/CONTRACT.md`](docs/CONTRACT.md)

---

# Error Contract

Provider-specific errors are translated into a provider-independent public contract.

| Condition | HTTP Status | Error Code |
|---|---:|---|
| Invalid input | `400` | `invalid_input` |
| Missing resource | `404` | `not_found` |
| Permission denied | `403` | `permission_denied` |
| Provider failure | `502` | `provider_error` |

Example:

```json
{
  "error": {
    "code": "not_found",
    "message": "Event not found"
  }
}
```

Google SDK objects, raw provider responses, credentials, tokens, and provider error messages are not exposed through the public API.

---

# Quick API Examples

The examples below use the real provider and therefore require Google Calendar configuration first.

## Create an Event

```bash
curl -i -X POST http://127.0.0.1:8000/events \
  -H "Content-Type: application/json" \
  -d '{"title":"OSPSD Test Event","start":"2026-10-22T10:00:00-04:00","end":"2026-10-22T11:00:00-04:00"}'
```

Expected:

```text
HTTP 201
```

Save the returned `id` for the following examples.

---

## Retrieve the Event

```bash
curl -i http://127.0.0.1:8000/events/<event-id>
```

Expected:

```text
HTTP 200
```

---

## List Events

```bash
curl -i "http://127.0.0.1:8000/events?limit=10"
```

`limit` defaults to `10` and accepts values from `1` through `100`.

Expected:

```text
HTTP 200
```

---

## Replace the Event

`PUT` is a complete replacement of the editable fields of an existing event.

```bash
curl -i -X PUT http://127.0.0.1:8000/events/<event-id> \
  -H "Content-Type: application/json" \
  -d '{"title":"OSPSD Replaced Event","start":"2026-10-22T12:00:00-04:00","end":"2026-10-22T13:00:00-04:00"}'
```

Expected:

```text
HTTP 200
```

`PUT` does not intentionally recreate a missing or deleted event. Missing events use the documented `404 not_found` response.

---

## Partially Update the Event

`PATCH` changes only the supplied fields.

```bash
curl -i -X PATCH http://127.0.0.1:8000/events/<event-id> \
  -H "Content-Type: application/json" \
  -d '{"title":"OSPSD Patched Event"}'
```

Expected:

```text
HTTP 200
```

Omitted fields remain unchanged.

---

## Delete the Event

```bash
curl -i -X DELETE http://127.0.0.1:8000/events/<event-id>
```

Expected:

```text
HTTP 204
```

A subsequent retrieval of the deleted event should return:

```text
HTTP 404
```

---

# Google Calendar Provider Setup

Google Calendar is the concrete provider used during normal provider-backed service execution.

Complete OAuth setup, permissions, credential locations, verification steps, known provider limitations, and cleanup instructions are documented in:

[`docs/PROVIDER.md`](docs/PROVIDER.md)

In summary, real-provider execution requires your own Google OAuth credentials.

Never commit:

- OAuth client credentials;
- access tokens;
- refresh tokens;
- `.env` files;
- local credential files;
- API keys.

Local provider secrets must remain outside version control.

Automated tests do not require these credentials.

---

# Testing

Run the complete credential-free test suite with:

```bash
uv run --locked python -m pytest
```

Or, with GNU Make:

```bash
make test
```

Tests cover:

- public HTTP behavior;
- input validation;
- domain models;
- controlled `EventProvider` substitution;
- Google provider translation;
- Level 5 failure behavior;
- malformed request handling;
- caching behavior;
- concurrency and invalidation regressions.

The detailed testing strategy and coverage map are documented in:

[`docs/TESTING.md`](docs/TESTING.md)

---

# Real-Provider Verification

Automated tests intentionally use controlled dependencies so they remain deterministic, credential-free, and network-free.

Real Google Calendar verification is performed separately.

The documented verification procedure exercises all six public operations and compares the expected API result with the observable Google Calendar result.

Follow:

[`docs/PROVIDER.md`](docs/PROVIDER.md)

Use disposable events for provider verification and clean them up when finished.

---

# Caching

The service includes the optional event-cache extension.

The cache uses:

- keys scoped by calendar ID and event ID;
- a 60-second TTL;
- bounded storage of 256 entries;
- deterministic eviction;
- write-aware invalidation/update behavior;
- concurrency protection against stale cache restoration.

The cache is process-local and is not shared across multiple service processes or deployments.

Implementation details, permitted staleness, provider-call behavior, and complexity are documented in:

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

Testing evidence is documented in:

[`docs/TESTING.md`](docs/TESTING.md)

---

# Repository Structure

```text
.
|-- .github/workflows/   # CI workflows
|-- app/                 # FastAPI, application, domain, cache, and provider code
|-- docs/                # Contract, architecture, provider, testing, and decision docs
|-- tests/               # Credential-free automated tests
|-- AGENTS.md            # Repository-wide contribution rules
|-- Makefile             # Canonical development commands
|-- pyproject.toml       # Project configuration and direct dependencies
|-- uv.lock              # Locked dependency versions
`-- README.md
```

The project intentionally favors clear boundaries and straightforward Python over unnecessary abstraction.

---

# Documentation

| Document | Purpose |
|---|---|
| [`docs/CONTRACT.md`](docs/CONTRACT.md) | Canonical public API, validation, and error behavior |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Architecture, provider boundary, operation cost, and caching |
| [`docs/PROVIDER.md`](docs/PROVIDER.md) | Google Calendar configuration and real-provider verification |
| [`docs/TESTING.md`](docs/TESTING.md) | Test strategy, coverage, and regression evidence |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Engineering decisions and trade-offs |
| [`docs/TEAM_AGREEMENT.md`](docs/TEAM_AGREEMENT.md) | Team workflow and collaboration |
| [`AGENTS.md`](AGENTS.md) | Repository-wide contribution rules |

---

# Code Quality

The canonical complete local check is:

```bash
make check
```

If Make is unavailable:

```bash
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy .
uv run --locked python -m pytest
uv run --locked python -m compileall app
uv run --locked python -c "import app.main"
```

To automatically format source files:

```bash
uv run --locked ruff format .
```

---

# Continuous Integration

GitHub Actions provides three required CI workflows:

- **Build** — verifies installation, compilation, and application import;
- **Format** — verifies formatting, linting, and configured static analysis;
- **Tests** — runs the automated behavioral suite.

Workflow definitions are located under:

```text
.github/workflows/
```

All required checks must pass before a change is considered release-ready.

---

# Contributing

Before making a change:

1. open or read the relevant GitHub issue;
2. read [`AGENTS.md`](AGENTS.md);
3. read the relevant section of [`docs/CONTRACT.md`](docs/CONTRACT.md);
4. inspect the existing implementation and tests;
5. understand the issue acceptance criteria.

A substantive change should normally include:

- implementation;
- focused regression or unit tests;
- integration tests when a meaningful boundary changes;
- relevant documentation updates.

Changes should be submitted through focused pull requests and reviewed by another teammate before merge.

Avoid unrelated refactoring in feature or bug-fix pull requests.

---

# Public Contract Policy

Public API behavior is treated as a contract.

Changes to:

- routes;
- HTTP methods;
- request models;
- response models;
- public fields;
- status codes;
- validation rules;
- documented errors;

must be intentional and reflected consistently in:

- implementation;
- automated tests;
- documentation.

The canonical source of truth is:

[`docs/CONTRACT.md`](docs/CONTRACT.md)

---

# Development Principles

Prefer:

- small changes;
- clear names;
- explicit types;
- focused functions;
- deterministic tests;
- established libraries;
- straightforward Python.

Avoid unnecessary:

- abstraction layers;
- wrapper hierarchies;
- factories;
- custom dependency-injection frameworks;
- speculative infrastructure;
- premature optimization.

A more complicated design should solve a concrete problem.

---

# License

This project is licensed under the [MIT License](LICENSE).
# OSPSD Team 2 — Calendar Service

Backend calendar service developed for NYU's **Open Source and Professional Software Development** course, Fall 2026.

The project exposes a provider-independent HTTP API for calendar operations using **Python** and **FastAPI**, with a real calendar provider integration behind the service.

The repository is designed to be easy for another developer to install, run, test, understand, and contribute to.

---

## Team Members

| NetID | Name |
|---|---|
| dxz207 | Dorien Zhang |
| my2658 | Maksym Yemelianenko |
| anf3003 | Alexander Freedman |
| ymh9084 | Yasmin Hassoobh |
| no2172 | Nicolas Ollivier |
| xl6081 | Xingjian Liu |

---

## Project Goals

This project aims to provide a small and maintainable backend service that:

- exposes calendar functionality through a documented HTTP API;
- keeps the public API independent from provider-specific SDK representations;
- integrates with a real calendar provider;
- validates behavior through focused unit and integration tests;
- maintains clear boundaries between HTTP, application, domain, and provider code;
- remains simple enough for contributors to understand and extend safely.

The project intentionally favors **clarity and simplicity over unnecessary abstraction**.

---

## Technology

- **Python 3.12**
- **FastAPI**
- **Pydantic**
- **pytest**
- **Ruff**
- **mypy**
- **uv**
- **GitHub Actions**

Additional provider-specific dependencies are documented with the provider integration.

---

## Repository Structure

The repository is organized by responsibility.

```text
.
|-- .github/workflows/   # Build, Format, and Tests CI
|-- app/                 # FastAPI, application, model, and Google integration code
|-- docs/                # Contract, architecture, provider, testing, and team docs
|-- tests/               # Unit and credential-free integration tests
|-- AGENTS.md            # Repository-wide contribution rules
|-- Makefile             # Canonical development commands
|-- pyproject.toml       # Project metadata and direct dependencies
|-- README.md
`-- uv.lock              # Cross-platform dependency lockfile
```

The exact source structure may evolve as the implementation develops.

Do not create additional architectural layers unless they solve a concrete problem.

---

## Documentation

Repository documentation is divided by responsibility.

| Document | Purpose |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Development rules for contributors and coding agents |
| [`docs/CONTRACT.md`](docs/CONTRACT.md) | Canonical public API and domain contracts |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Architecture, code boundaries, and dependency direction |
| [`docs/TESTING.md`](docs/TESTING.md) | Testing strategy and test coverage map |
| [`docs/PROVIDER.md`](docs/PROVIDER.md) | Provider-specific behavior, configuration, and assumptions |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Significant technical decisions and trade-offs |
| [`docs/TEAM_AGREEMENT.md`](docs/TEAM_AGREEMENT.md) | Team workflow and collaboration expectations |

Before implementing a feature, read `AGENTS.md` and the documentation relevant to the issue.

---

## Setup

The supported Python version is **Python 3.12**, matching CI. The repository uses
[uv](https://docs.astral.sh/uv/getting-started/installation/) to manage Python,
the virtual environment, and locked dependencies consistently across platforms.

### 1. Clone the repository

```bash
git clone <repository-url>
cd <repository-name>
```

### 2. Install uv

Install the repository's required uv version using the appropriate official
standalone installer.

macOS and Linux:

```bash
curl -LsSf https://astral.sh/uv/0.12.17/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/0.12.17/install.ps1 | iex"
```

Other supported installation methods are listed in uv's
[official installation instructions](https://docs.astral.sh/uv/getting-started/installation/).
Confirm the required version is available:

```bash
uv --version
```

The command should report `uv 0.12.17`.

### 3. Install Python and dependencies

```bash
uv python install 3.12
uv sync --locked
```

No virtual-environment activation is required; use `uv run` for project
commands. Direct dependencies are declared in `pyproject.toml`, and all resolved
dependencies are pinned in `uv.lock` for reproducible installation.

---

## Provider Configuration

The service connects to an external calendar provider.

Provider authentication, required permissions, credential setup, and known limitations are documented in:

[`docs/PROVIDER.md`](docs/PROVIDER.md)

Never commit:

- OAuth credentials;
- access tokens;
- refresh tokens;
- `.env` files;
- local credential files;
- API keys.

Local credentials must remain outside version control.

---

## Running the Service

From the repository root:

```bash
uv run --locked uvicorn app.main:app --reload
```

By default, FastAPI exposes interactive API documentation through Swagger UI at:

```text
http://127.0.0.1:8000/docs
```

The exact public API contract is documented in:

[`docs/CONTRACT.md`](docs/CONTRACT.md)

List up to two events from the configured calendar (200 with a JSON array):

```bash
curl -i 'http://127.0.0.1:8000/events?limit=2'
```

Listing defaults to 10 events and accepts limits from 1 to 100. See the contract
for supported event shapes and provider-page limitations.
For Nicolas's complete event replacement operation, see the runnable
[`PUT /events/{event_id}` example](docs/CONTRACT.md#replace-event--nicolas-ollivier-51-operation-4).
All editable fields are required. Write access and renewed OAuth consent are
described in [provider setup](docs/PROVIDER.md#authentication).

### Partially update an event

Yasmin's `PATCH /events/{event_id}` changes only supplied fields:

```bash
curl -i -X PATCH http://127.0.0.1:8000/events/your-test-event-id \
  -H 'Content-Type: application/json' -d '{"title":"Updated meeting"}'
```

Expect 200 with the updated Event and unchanged omitted fields. See the
[PATCH contract](docs/CONTRACT.md#partially-update-event--yasmin-hassoobh-51-operation-5)
and [verification/cleanup instructions](docs/PROVIDER.md#partial-update-verification).

### Create an event

After completing provider configuration, create a titled, timed event with:

```bash
curl -i -X POST http://127.0.0.1:8000/events \
  -H "Content-Type: application/json" \
  -d '{"title":"Team Meeting","start":"2026-10-22T10:00:00-04:00","end":"2026-10-22T11:00:00-04:00"}'
```

The expected response is HTTP 201 with the created event's generated `id`,
`title`, `start`, and `end`. See [`docs/PROVIDER.md`](docs/PROVIDER.md) for
real-provider verification and cleanup.

---

## Testing

The project uses `pytest`. Run the complete fast test suite on any supported
platform with:

```bash
uv run --locked python -m pytest
```

If GNU Make is installed, `make test` runs the same command through uv:

```bash
make test
```

The focused test files under `tests/` cover the public model, provider mapping,
Google client behavior, and the HTTP integration path. The detailed coverage map
is maintained in [`docs/TESTING.md`](docs/TESTING.md).

### Unit Tests

Unit tests verify small, focused pieces of behavior in isolation.

Unit tests must be fast, deterministic, and independent of real provider credentials or network access.

### Integration Tests

Integration tests verify meaningful boundaries between components.

Normal integration tests should use controlled dependencies and should not require access to the real provider.

### Real Provider Verification

Tests or verification requiring the real provider are kept separate from the normal fast test suite.

See:

[`docs/TESTING.md`](docs/TESTING.md)

and:

[`docs/PROVIDER.md`](docs/PROVIDER.md)

for current instructions.

---

## Code Quality

Run every required local check on any supported platform with:

```bash
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy .
uv run --locked python -m pytest
uv run --locked python -m compileall app
uv run --locked python -c "import app.main"
```

If GNU Make is installed, `make check` runs this complete sequence.

### Check formatting

```bash
uv run --locked ruff format --check .
```

### Format code

```bash
uv run --locked ruff format .
```

### Lint

```bash
uv run --locked ruff check .
```

### Type check

```bash
uv run --locked mypy .
```

Contributors should run the relevant checks locally before pushing.

---

## Continuous Integration

GitHub Actions automatically verifies changes.

Three independent CI workflows are maintained:

### Build

Checks that the project can be installed, compiled, and loaded from a clean environment.

```text
.github/workflows/build.yml
```

### Format

Checks formatting, linting, and configured static analysis.

```text
.github/workflows/format.yml
```

### Tests

Runs the project's automated behavioral tests.

```text
.github/workflows/tests.yml
```

Required CI checks:

```text
✓ Build
✓ Format
✓ Tests
```

The workflows run on pushes and pull requests.

All required checks must pass before a change is considered ready to merge.

---

## Contributing

Work should begin with a GitHub issue describing the behavior or problem being addressed.

Before implementation:

1. read the issue completely;
2. read `AGENTS.md`;
3. review the relevant public contract;
4. inspect existing related code;
5. understand the acceptance criteria.

Each implementation should generally include:

- the implementation itself;
- focused unit tests;
- integration tests when a meaningful boundary is affected;
- relevant documentation updates.

Submit changes through a focused pull request linked to the corresponding issue.

Avoid unrelated refactoring or cleanup in feature pull requests.

At least one teammate other than the author should review substantive changes before merge.

See [`AGENTS.md`](AGENTS.md) for the full development and review requirements.

---

## Public Contracts

Public API behavior is treated as a contract.

Changes to:

- routes;
- HTTP methods;
- request models;
- response models;
- public fields;
- status codes;
- documented error behavior;

must be intentional.

A contract change requires corresponding updates to:

- documentation;
- implementation;
- tests.

The canonical source of truth is:

[`docs/CONTRACT.md`](docs/CONTRACT.md)

---

## Development Principles

Contributors should favor:

- small and understandable changes;
- clear names;
- explicit types;
- focused functions;
- meaningful tests;
- established libraries;
- straightforward Python.

Avoid unnecessary:

- abstraction layers;
- wrapper classes;
- factories;
- dependency-injection frameworks;
- custom infrastructure;
- premature optimization;
- speculative architecture.

A more complicated design should have a concrete reason to exist.

---

## License

This project is licensed under the [MIT License](LICENSE).

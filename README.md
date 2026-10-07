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
|-- README.md
`-- requirements.txt     # Pinned Python dependencies
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

The supported Python version is **Python 3.12**, matching CI. Confirm the active
interpreter before creating the environment:

```bash
python --version
```

### 1. Clone the repository

```bash
git clone <repository-url>
cd <repository-name>
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it.

macOS/Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Dependencies are pinned in `requirements.txt` for reproducible installation.

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
python -m uvicorn app.main:app --reload
```

By default, FastAPI exposes interactive API documentation through Swagger UI at:

```text
http://127.0.0.1:8000/docs
```

The exact public API contract is documented in:

[`docs/CONTRACT.md`](docs/CONTRACT.md)

---

## Testing

The project uses `pytest`. Run the complete fast test suite through the canonical
Makefile target:

```bash
make test
```

If GNU Make is unavailable, run the equivalent Python command:

```bash
python -m pytest
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

Run every required local check with:

```bash
make check
```

### Check formatting

```bash
make format-check
```

### Format code

```bash
make format
```

### Lint

```bash
make lint
```

### Type check

```bash
make typecheck
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

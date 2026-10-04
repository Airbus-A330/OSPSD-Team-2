# AGENTS.md

Repository-wide instructions for coding agents and contributors.

The goal of this repository is to produce a small, clear, well-tested Python backend service that is easy for another developer to understand, run, extend, and review.

Favor **correctness, readability, simplicity, and maintainability** over cleverness or unnecessary abstraction.

---

## 1. Canonical Documentation

Before implementing a task, consult the relevant source of truth:

- `README.md` — project setup, usage, and repository overview
- `docs/CONTRACT.md` — public behavior and domain contracts
- `docs/ARCHITECTURE.md` — module responsibilities and dependency boundaries
- `docs/TESTING.md` — testing strategy and coverage map
- `docs/PROVIDER.md` — provider-specific behavior and verified assumptions
- `docs/DECISIONS.md` — significant technical decisions
- `docs/TEAM_AGREEMENT.md` — collaboration expectations
- `AGENTS.md` — repository-wide development rules

Do not maintain conflicting copies of the same information.

Link to the canonical source instead of duplicating it.

---

## 2. General Principles

When making changes to this repository:

- Read the relevant code and documentation before editing.
- Understand the applicable contract before implementing behavior.
- Make the smallest change that correctly satisfies the task.
- Prefer simple, explicit code over clever or highly abstract code.
- Do not overengineer.
- Do not introduce infrastructure, abstractions, patterns, or dependencies without a concrete need.
- Keep changes focused on the assigned issue.
- Do not modify unrelated code.
- Preserve existing behavior unless the task explicitly requires a contract change.
- Every change should be understandable and explainable by a student contributor.
- Avoid unnecessary lines of code, helper layers, wrapper classes, or duplicated abstractions.
- Remove unused code, imports, dependencies, and temporary debugging artifacts.

When multiple approaches are valid, prefer the one that:

1. is easiest to understand;
2. has the fewest moving parts;
3. is easiest to test;
4. preserves clear boundaries;
5. introduces the least unnecessary complexity.

---

## 3. Python Standards

Use modern, idiomatic Python.

### General Style

- Follow PEP 8.
- Use descriptive names.
- Prefer clarity over brevity.
- Keep functions small and focused.
- Keep classes focused on one responsibility.
- Avoid deeply nested logic.
- Prefer early returns when they improve readability.
- Avoid unnecessary global state.
- Avoid magic values when a named constant improves clarity.
- Never use mutable default arguments.
- Avoid `Any` unless there is a clear reason.
- Avoid broad `except Exception` handlers unless there is a documented justification.
- Do not silently ignore errors.
- Keep imports at the top of the file unless there is a concrete reason not to.
- Prefer standard-library functionality when it solves the problem clearly.
- Use established Python conventions rather than inventing repository-specific patterns without need.

### Typing

Use type hints for:

- public functions;
- public methods;
- function parameters;
- return values;
- important internal boundaries.

Prefer explicit types over loosely structured dictionaries where practical.

Use:

- Pydantic models for API request and response boundaries;
- dataclasses or small typed objects for internal domain data when useful;
- standard Python collection types appropriately.

Do not create a custom type or class when an ordinary Python type communicates the intent clearly.

---

## 4. Docstrings and Comments

Python uses **docstrings** for structured code documentation.

Use Google-style docstrings for:

- public modules;
- public classes;
- non-trivial public functions.

Example:

```python
def get_event(event_id: str) -> Event:
    """Retrieve an event by its identifier.

    Args:
        event_id: Unique identifier of the event.

    Returns:
        The event represented by the service's public domain model.

    Raises:
        EventNotFoundError: If the requested event does not exist.
    """
```

Do not add docstrings merely to repeat obvious code.

Good documentation should explain:

- purpose;
- important assumptions;
- non-obvious behavior;
- meaningful inputs and outputs;
- meaningful exceptions;
- architectural reasoning when necessary.

### Comments

Comments should primarily explain **why**, not **what**.

Avoid comments such as:

```python
# Increment count by one.
count += 1
```

Use comments when the reasoning would otherwise be unclear.

Do not leave:

- commented-out code;
- temporary debugging comments;
- stale TODOs;
- large explanatory essays inside implementation files.

If a decision requires substantial explanation, document it in the appropriate project documentation.

---

## 5. Code Structure

Keep the repository structure simple and predictable.

Code should be separated by responsibility where doing so improves clarity.

A possible structure is:

```text
app/
    main.py
    models/
    routes/
    services/
    providers/

tests/
    unit/
    integration/

docs/
```

This is a guideline, not a requirement to create directories prematurely.

Do not create a package, directory, interface, service, manager, factory, or abstraction until actual behavior justifies it.

Prefer fewer well-organized modules over many tiny files.

### Responsibility Boundaries

Keep these responsibilities separate when practical:

- HTTP/API handling;
- application/domain logic;
- provider-specific integration;
- models and schemas;
- configuration;
- testing.

FastAPI route handlers should remain thin.

A route should generally:

1. receive and validate HTTP input;
2. call application behavior;
3. return the public response.

Do not place substantial provider-specific or business logic directly inside route handlers.

---

## 6. API Design

FastAPI is the HTTP framework for this repository.

Public API behavior is a contract.

Treat the following as part of that contract:

- HTTP methods;
- route paths;
- path parameters;
- query parameters;
- request body shape;
- response body shape;
- field names;
- field types;
- status codes;
- documented error behavior.

Do not change a public API contract casually.

If an issue requires a contract change:

1. identify the existing contract;
2. explain the proposed change;
3. update relevant tests;
4. update relevant documentation;
5. clearly mention the change in the pull request.

### Provider Boundaries

The public API must describe the service's own domain rather than exposing an external provider's SDK representation.

Do not:

- return raw SDK objects;
- expose unnecessary provider-specific fields;
- require callers to understand provider-specific request formats;
- allow provider SDK types to leak unnecessarily through application layers.

Translate provider data into the service's own public models.

Keep provider-specific code localized.

---

## 7. Simplicity and Avoiding Overengineering

This repository should remain intentionally small.

Do not introduce patterns simply because they are common in larger production systems.

Avoid unnecessary:

- factory classes;
- manager classes;
- repository patterns;
- service layers that merely forward one call;
- dependency-injection frameworks;
- plugin systems;
- event buses;
- queues;
- caches;
- custom frameworks;
- generic abstractions;
- large inheritance hierarchies.

An abstraction should exist because it provides a concrete benefit.

Before introducing one, ask:

- What duplication or coupling does this remove?
- What behavior does this make easier to understand?
- What current requirement does this support?
- Is the abstraction simpler than the code it replaces?

If there is no clear answer, keep the implementation simpler.

Do not build infrastructure merely because it may be useful later.

---

## 8. Readability

Optimize code for the next contributor reading it.

Code should make it easy to understand:

- what a function does;
- what inputs it expects;
- what it returns;
- what state it changes;
- what external systems it communicates with;
- what failures can occur.

Prefer:

```python
event = provider.get_event(event_id)
```

over unnecessary indirection such as:

```python
event = provider_manager.execute_event_retrieval_operation(
    EventRetrievalRequest(identifier=event_id)
)
```

unless the additional structure provides a real benefit.

Use names that communicate intent.

Prefer:

```python
calendar_id
event_id
provider_event
```

over:

```python
cid
eid
data
obj
thing
```

---

## 9. Testing Philosophy

Tests are part of the implementation and are required evidence that code satisfies its contract.

The contributor or agent implementing a feature is responsible for writing or updating the tests for that feature.

Tests should prove behavior, not merely execute code.

### Testing Hierarchy

Use the smallest test boundary capable of proving the behavior.

Prefer:

1. **Unit tests** for isolated behavior.
2. **Integration tests** for meaningful interactions between components.
3. **End-to-end or real-provider verification** when behavior must be established against the real external system.

Do not replace a focused unit test with a slower integration test when isolation is sufficient.

Do not rely only on unit tests when correctness depends on a boundary between components.

---

## 10. Unit Tests

Unit tests must be:

- small;
- fast;
- deterministic;
- focused on a specific feature or behavior;
- independent from network access;
- independent from real credentials;
- independent from unrelated application state.

Each unit test should answer one clear behavioral question.

Prefer several focused tests over one large test exercising many unrelated behaviors.

Examples of appropriate unit-test questions:

- Does valid input produce the expected domain model?
- Does invalid input fail validation?
- Does a provider response map correctly into the public representation?
- Does a transformation preserve required fields?
- Does a controlled dependency response produce the expected application result?

### Unit-Test Boundaries

Mock or fake external boundaries when necessary, including:

- provider SDK calls;
- outbound HTTP;
- OAuth;
- external services;
- nondeterministic resources.

Do not mock the function or class whose behavior is actually under test.

Avoid excessive mocking of internal implementation details.

Tests should generally continue to pass after an internal refactor that preserves the contract.

### Assertions

Prefer meaningful assertions against complete results when practical.

Example:

```python
assert event == Event(
    id="event-123",
    title="Team Meeting",
    start=expected_start,
    end=expected_end,
)
```

Avoid tests that primarily assert:

- private method calls;
- private variables;
- incidental internal call order;
- implementation details not included in the contract.

---

## 11. Contract Tests

Public contracts must have explicit tests.

When code implements or changes a documented contract, tests must verify the parts callers are allowed to rely on.

For an HTTP API, applicable contract tests should verify:

- HTTP method;
- route;
- required parameters;
- request schema;
- response schema;
- response field names;
- response field types;
- status codes;
- documented errors.

For an internal provider-independent interface, applicable tests should verify:

- accepted inputs;
- returned domain types;
- documented state changes;
- documented assumptions;
- documented failure behavior.

A public contract change requires corresponding test and documentation changes.

Do not change implementation behavior first and silently adjust the contract afterward.

---

## 12. Integration Tests

Integration tests verify that multiple components work correctly together across a meaningful boundary.

Integration tests are **not groups of unit tests**.

Use an integration test when the important question is something such as:

- Does a FastAPI route correctly communicate with application logic?
- Does application logic correctly use a provider boundary?
- Does provider data travel correctly through translation and serialization?
- Does configuration correctly supply the expected implementation?
- Do two modules agree on the same contract?

A typical integration flow may look like:

```text
HTTP request
    ↓
FastAPI route
    ↓
application logic
    ↓
controlled provider
    ↓
domain model
    ↓
HTTP response
```

Integration tests should focus on meaningful component boundaries rather than retesting every detailed behavior already covered by unit tests.

### Controlled Dependencies

Credential-free integration tests should use controlled dependencies such as:

- fakes;
- fixtures;
- test implementations;
- mocks at true external boundaries.

This keeps integration tests:

- repeatable;
- fast;
- deterministic;
- suitable for normal CI;
- independent from provider availability.

---

## 13. Real Provider and End-to-End Tests

Real-provider tests serve a different purpose from ordinary unit and integration tests.

Use them to verify assumptions such as:

- authentication works;
- the selected provider operation behaves as expected;
- identifiers behave as documented;
- provider response fields match documented assumptions;
- the complete system works against the real integration.

Real-provider tests must be clearly separated from normal fast tests.

The default CI pipeline must not depend on:

- personal credentials;
- OAuth token files;
- manually prepared personal account state;
- external provider availability.

Provider tests requiring credentials should be explicitly opt-in or run in a separately configured workflow.

---

## 14. Test Organization

Organize tests around meaningful behavior.

A reasonable structure is:

```text
tests/
    unit/
    integration/
    e2e/
```

Only create directories that are actually useful.

Examples of descriptive test files:

```text
test_event_model.py
test_event_mapping.py
test_event_routes.py
test_provider_client.py
test_event_workflow.py
```

Test function names should describe observable behavior.

Prefer:

```python
def test_get_event_returns_public_event_model():
    ...
```

over:

```python
def test_get_event():
    ...
```

Use `pytest`.

Prefer plain pytest test functions and fixtures over `unittest.TestCase` unless there is a concrete reason otherwise.

---

## 15. Test Quality

A test should have a plausible reason to fail if the implementation becomes incorrect.

Do not add meaningless tests merely to increase coverage.

Avoid tests such as:

```python
assert result is not None
```

when the contract promises substantially more behavior.

For each feature, consider applicable cases from:

- normal success;
- missing input;
- malformed input;
- invalid input;
- boundary values;
- provider rejection;
- unavailable dependency;
- malformed provider data;
- repeated operations;
- state before and after the operation.

Do not invent requirements that the documented contract does not impose.

Coverage is useful as a signal, not as the objective.

Prefer meaningful contract coverage over artificially maximizing the coverage percentage.

---

## 16. Regression Tests

When fixing a bug:

1. reproduce the defect with a test when practical;
2. confirm the test fails before the fix;
3. implement the smallest appropriate correction;
4. confirm the test passes afterward;
5. retain the test to prevent recurrence.

A bug fix without a regression test should have an explicit reason when reliable automated verification is practical.

---

## 17. Developer Commands

The repository uses a root-level `Makefile` as the canonical interface for common development tasks.

Run commands from the repository root.

Preferred commands:

```bash
make format
make format-check
make lint
make typecheck
make test
make build
make check
```

### Command Meanings

#### `make format`

Formats Python source using the configured formatter.

This command may modify files.

#### `make format-check`

Checks whether source files are correctly formatted without modifying them.

#### `make lint`

Runs configured static lint checks.

#### `make typecheck`

Runs configured static type checking.

#### `make test`

Runs the default automated test suite.

This should include unit tests and credential-free integration tests as appropriate.

#### `make build`

Verifies that the Python project can compile and that its application entrypoint can be imported successfully.

#### `make check`

Runs the complete required local verification suite.

It should represent the checks a contributor is expected to pass before considering work complete.

### Makefile Rules

Agents and contributors should prefer Makefile targets over duplicating raw tool commands in documentation, scripts, or pull-request instructions.

Local development and CI should invoke the same canonical commands where practical.

If the underlying tool or command changes, update the Makefile rather than creating competing command definitions elsewhere.

Do not bypass a Makefile target merely to avoid a failing check.

---

## 18. Continuous Integration

GitHub Actions is the repository's continuous-integration system.

The repository maintains three independent required workflows:

```text
.github/workflows/
    build.yml
    format.yml
    tests.yml
```

The required checks are:

```text
Build
Format
Tests
```

Each workflow should have a single clear responsibility.

All required checks must pass before a substantive change is considered ready to merge.

Do not:

- remove a required check to make a pull request pass;
- weaken a check without a documented reason;
- hide failures with `continue-on-error`;
- silently skip relevant tests;
- disable lint rules merely to silence valid problems.

If CI fails, fix the underlying issue or document why the CI configuration itself is incorrect.

---

## 19. Build CI

File:

```text
.github/workflows/build.yml
```

The **Build** workflow verifies that the project can be constructed and loaded successfully from a clean environment.

The workflow should delegate to:

```bash
make build
```

The build should verify, as applicable:

- Python configuration succeeds;
- declared dependencies install successfully;
- Python source compiles;
- the application entrypoint can be imported.

Conceptually:

```text
clean checkout
    ↓
configure Python
    ↓
install declared dependencies
    ↓
make build
```

Do not add unrelated behavioral tests, formatting checks, or linting to the Build workflow.

The Build workflow answers:

> Can a clean environment install and load this project successfully?

---

## 20. Format CI

File:

```text
.github/workflows/format.yml
```

The **Format** workflow verifies formatting and static code quality.

It should run the canonical Makefile targets:

```bash
make format-check
make lint
make typecheck
```

Use Ruff for Python formatting and linting unless the repository explicitly adopts another tool.

Use mypy for static type checking when configured.

CI must only **check** formatting.

It must not automatically rewrite committed source code.

Formatting changes should be made locally using:

```bash
make format
```

The Format workflow answers:

> Does the submitted code meet the repository's formatting, linting, and static-quality standards?

---

## 21. Tests CI

File:

```text
.github/workflows/tests.yml
```

The **Tests** workflow verifies program behavior.

It should run:

```bash
make test
```

The default CI test suite should include:

- focused unit tests;
- credential-free integration tests.

Normal CI must not require:

- live OAuth credentials;
- personal provider accounts;
- external provider availability.

Real-provider tests should be explicitly opt-in or isolated from normal CI.

The Tests workflow answers:

> Does the implementation still satisfy its tested behavioral contracts?

---

## 22. GitHub Actions Practices

Required CI workflows should run on:

- pushes;
- pull requests.

A simple trigger is appropriate:

```yaml
on:
  push:
  pull_request:
```

Use standard GitHub-hosted Linux runners unless the repository explicitly documents another requirement.

Prefer:

```yaml
runs-on: ubuntu-latest
```

Do not require a self-hosted runner unless there is a concrete project need.

### Keep CI Simple

Avoid unnecessary:

- matrix builds;
- multiple operating systems;
- scheduled runs;
- deployment automation;
- large runners;
- redundant jobs.

CI configuration should remain proportional to the project.

### Cancel Outdated Runs

When practical, use GitHub Actions concurrency controls to cancel outdated runs for the same workflow and branch.

Example:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

This avoids wasting CI resources on obsolete commits.

### Reproducibility

CI must run correctly from a fresh checkout.

It must not depend on:

- developer-specific filesystem paths;
- previous workflow runs;
- undeclared local packages;
- personal tokens;
- uncommitted files;
- test execution order.

Dependencies required by CI should be formally declared by the project.

---

## 23. Local Verification

Contributors should run relevant checks locally before pushing when practical.

For the full local verification suite:

```bash
make check
```

Individual checks may be run with:

```bash
make build
make format-check
make lint
make typecheck
make test
```

Formatting source code:

```bash
make format
```

Do not claim a change is complete if known required checks are failing.

CI provides clean-environment verification; it does not replace local development discipline.

---

## 24. Error Handling

Failures should be explicit.

Do not:

- silently swallow exceptions;
- return successful responses for failed operations;
- expose raw provider exceptions directly through the public API;
- expose credentials or sensitive provider information in errors;
- rely on vague fallback behavior.

Catch exceptions only where the code can meaningfully:

- translate them;
- add context;
- recover;
- or produce documented public behavior.

Use specific exception types when they improve clarity.

---

## 25. Security and Secrets

Never commit:

- API keys;
- OAuth client secrets;
- access tokens;
- refresh tokens;
- `.env` files;
- local credential files;
- authorization headers;
- test-account credentials.

Use environment variables or ignored local configuration files.

Do not log sensitive credentials.

If a feature requires new configuration:

- document the variable or file;
- explain how it is obtained;
- keep the secret itself outside the repository.

---

## 26. Dependencies

Prefer the Python standard library when it solves the problem clearly.

Use established third-party libraries when they provide meaningful value.

Before adding a dependency:

1. check whether an existing dependency already solves the problem;
2. determine whether the standard library is sufficient;
3. confirm the dependency is appropriate for the project;
4. keep the dependency narrowly scoped to the problem.

Do not add libraries merely to avoid writing a few straightforward lines of Python.

Pin or lock dependencies according to the project's chosen dependency-management strategy.

Adding or removing a dependency should be explicitly mentioned in the pull request.

---

## 27. Git and Pull Request Scope

Keep changes small and reviewable.

Each issue should generally correspond to a focused pull request.

A pull request should contain:

- the implementation;
- tests for that implementation;
- relevant documentation changes.

Do not mix unrelated cleanup or refactoring into a feature pull request.

Link the pull request to its GitHub issue.

Use clear commit messages written or reviewed by the student contributor.

Do not generate large amounts of unrelated code.

### Pull Request Verification

Every implementation pull request should state:

#### Tests Added or Changed

Describe which tests verify the implementation.

#### Verification Performed

Prefer the canonical command:

```text
make check
```

If only targeted checks were run, list them explicitly.

#### Contract Impact

State either:

```text
Public contract unchanged.
```

or clearly identify the intentional contract change.

#### Known Limitations

Document behavior that remains unsupported or unverified.

---

## 28. Human Review

Agent-generated code is not automatically trusted.

Every substantive change must have a student owner who:

- understands the implementation;
- reviews generated code;
- verifies the relevant tests;
- can explain the design;
- can maintain the code afterward.

At least one teammate other than the author should review substantive changes before merging.

Review:

- implementation;
- tests;
- public contracts;
- dependency changes;
- configuration changes;
- documentation;
- CI changes.

Do not approve a change solely because CI is green.

---

## 29. Working From GitHub Issues

When implementing a GitHub issue:

1. Read the entire issue.
2. Read all linked specifications and documentation.
3. Identify the required public behavior.
4. Identify explicit non-goals.
5. Inspect existing related code before editing.
6. Implement only what is necessary to satisfy the issue.
7. Add focused unit tests for the behavior implemented.
8. Add or update integration tests when the change crosses a meaningful component boundary.
9. Run relevant local checks.
10. Update relevant documentation.
11. Report assumptions, limitations, or deviations in the pull request.

If the issue contains a contract or acceptance criteria, treat them as authoritative unless they conflict with another documented repository contract or assignment requirement.

If a task is ambiguous in a way that could materially change public behavior, do not guess.

Raise the ambiguity for human review.

---

## 30. Definition of Done

A change is complete when:

- the requested behavior is implemented;
- the implementation is readable and appropriately typed;
- focused unit tests cover the feature's important behavior;
- relevant integration tests cover important component boundaries;
- public contracts are represented by meaningful tests;
- documentation reflects the implementation;
- no secrets or unrelated changes were introduced;
- unnecessary code and dependencies were removed;
- the change is focused enough for another teammate to review;
- a student contributor can explain what the code does and why it is designed that way;
- all required CI checks pass.

The required repository checks are:

```text
✓ Build
✓ Format
✓ Tests
```

Before considering a change complete, contributors should normally be able to run:

```bash
make check
```

successfully.

A green CI status does not prove that a design is good, but a change with failing required CI checks is not complete.

The goal is not maximum abstraction, maximum test count, maximum coverage, or maximum lines of code.

The goal is:

**small, correct, readable, testable, maintainable software.**
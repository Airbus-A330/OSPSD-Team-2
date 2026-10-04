# Public Contract

This document is the canonical source of truth for the service's public behavior.

Code, tests, examples, and other documentation must remain consistent with this contract.

Do not change a public contract as a side effect of implementation. Contract changes must be intentional, documented, tested, and reviewed.

---

## Contract Principles

The public API describes the domain of this service, not the representation used by an external provider.

Callers should not need to understand:

- provider SDK types;
- provider-specific request objects;
- provider-specific response objects;
- authentication implementation details;
- unnecessary provider metadata.

Provider-specific data must be translated into the service's public models before it reaches callers.

---

## HTTP API

Document every public operation using the following structure.

### `<Operation Name>`

**Purpose**

Describe what the operation means to a caller.

**Method**

```text
GET | POST | PATCH | PUT | DELETE
```

**Route**

```text
/path
```

**Path parameters**

| Name | Type | Required | Meaning |
|---|---|---:|---|
| | | | |

**Query parameters**

| Name | Type | Required | Default | Meaning |
|---|---|---:|---|---|
| | | | | |

**Request body**

If applicable, document the public request model.

**Successful response**

```json
{}
```

**Success status**

```text
200 OK
```

**Observable behavior**

Document what callers are allowed to rely on.

**State changes**

State whether the operation:

- reads external state;
- creates state;
- modifies state;
- deletes state;
- has no external side effect.

**Errors**

Document only error behavior currently guaranteed by the service.

---

## Domain Models

Public domain models belong here.

For each model, document:

- field name;
- type;
- whether it is required;
- meaning;
- important invariants.

Example:

### Event

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | `string` | yes | Service-visible event identifier |
| `title` | `string` | yes | Human-readable event title |
| `start` | `string` | yes | Event start according to the documented time representation |
| `end` | `string` | yes | Event end according to the documented time representation |

> This table is illustrative until the team formally approves the Event contract.

---

## Contract Change Rules

A public contract change requires:

1. an intentional decision by the team;
2. updated contract documentation;
3. updated implementation;
4. updated unit or contract tests;
5. updated integration tests where applicable;
6. an explicit note in the pull request.

Do not modify the public API merely to match an external provider's representation.

---

## Assumptions

Record assumptions that affect observable behavior here.

For each assumption, include:

- the assumption;
- why it currently exists;
- evidence supporting it, if available;
- what would cause the team to revisit it.

Do not silently encode uncertain assumptions into implementation.
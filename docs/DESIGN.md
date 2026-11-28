# Team 2 Personal Agent — Design

This document explains the current system and the Milestone 2 target from a new
reader's perspective. It describes design and responsibility boundaries; it is
not an execution log. Historical milestone notes are preserved in
[DESIGN_HISTORY.md](DESIGN_HISTORY.md), and verification status is tracked in
[READINESS.md](READINESS.md).

## 1. Purpose and product context

Team 2 is building **Kickoff Handoff**, a personal agent for leads of small
student software teams. A lead describes a project kickoff once, reviews the
exact proposed changes, and—after authenticated approval—creates a Dropbox
document, a Trello issue, and a Google Calendar event. The same user can later
ask what happened and see confirmed, failed, uncertain, and unattempted steps.

The product is intentionally narrower than a general assistant. The canonical
scenario definitions, launch measures, and non-goals are in the
[product brief](HW3_MS2_PRODUCT_BRIEF.md).

## 2. Users and key scenarios

The pilot user is a student software-team lead who controls the three provider
destinations.

- **S1 — Set up a kickoff:** collect complete inputs, show an exact proposal,
  require approval, then execute document → issue → calendar once.
- **S2 — Check a previous kickoff:** return durable per-step outcomes and known
  references without performing provider writes.

The existing manual interface demonstrates S1 against the composed API. Real
multi-user identity, durable approval, durable status, and launch evidence are
integration gates, not capabilities that the current branch claims complete.

## 3. System architecture

```text
Browser
  |
  v
Python web interface (client only)
  |                         |
  | manual workflow         | natural-language request/status
  v                         v
Team 2 API service       Agent service
  |                         |
  |                         +-- model adapter (bounded structured decision)
  |                         +-- tool client (Team 2 API only)
  v
ProjectKickoffWorkflow
  +-- shared Cloud Storage contract -> Team 3 Dropbox package
  +-- shared Issue Tracker contract -> Team 4 Trello package
  +-- shared Calendar contract      -> Team 2 Google provider
```

The browser never receives provider credentials and never calls providers or a
database directly. The interface calls Team 2 services; the agent's tools call
the Team 2 API. Provider SDKs remain behind their shared contract adapters.

The agent implementation is developed separately and is not present as tracked
source on this branch. The interface therefore treats agent and account clients
as explicit integration boundaries and fails closed when unavailable.

## 4. Component responsibilities

| Component | Responsibility | Must not do |
| --- | --- | --- |
| `interface/` | Render the scenario, exact proposal, progress, and actionable results; call backend services | Call providers, store credentials, or treat browser state as identity/approval |
| Agent service | Bound model turns/time/tools, persist run status, propose exact actions, and call approved tools | Let model output bypass policy, identity, or approval enforcement |
| `app/api/` | Parse HTTP input, authenticate at the service boundary, and serialize contract responses | Contain provider-specific behavior |
| `ProjectKickoffWorkflow` | Execute the fixed three-step sequence and preserve per-step outcomes | Select provider implementations or retry uncertain writes |
| Composition modules | Select and construct configured vertical implementations | Put selection conditionals inside workflow behavior |
| Provider adapters | Translate shared requests/results/errors and own provider clients | Expose SDK objects or raw provider failures |
| Durable state/approval layer | Own users, runs, immutable proposals, approval claims, and recovery | Trust a browser session ID or model assertion as user identity |

## 5. Request and agent execution trace

For manual S1, the interface receives user input, shows the exact values for
review, and submits one request to `POST /workflows/project-kickoff`. The API
constructs configured verticals before any write. The workflow creates the
document, then issue, then event, and returns one combined result.

For an agent-driven S1 request, the target flow is:

1. derive the user from verified credentials;
2. ask the model for a bounded, schema-validated decision;
3. clarify missing values or persist an exact proposal;
4. show provider, target, before/after values, and effects;
5. bind approval to the current proposal digest and authenticated user;
6. atomically claim the approved run for execution;
7. invoke the same Team 2 workflow API once;
8. persist each result and return it to the interface.

The model may propose or request a tool. Deterministic code validates identity,
ownership, approval, time/tool budgets, arguments, and policy before dispatch.

## 6. Identity and trust boundaries

The browser is untrusted input. A server-side session may support navigation but
is not proof of identity. The backend must derive the user from verified
credentials, scope every run/approval/provider connection to that user, and
reject cross-user identifiers before any provider call.

Provider OAuth material and service API keys are runtime secrets. They are never
included in prompts, tool results, browser payloads, telemetry, or repository
evidence. The model is also untrusted: its text and tool arguments are validated
like any other caller input.

## 7. Approval and execution model

Approval applies to an immutable action artifact: operation, target, exact
values, affected providers, and a digest. Editing or regenerating the proposal
invalidates prior approval. Rejection performs no write. A durable atomic claim
prevents two workers or a replayed approval from executing the same proposal.

The current interface can display proposals and persist rejection through agent
cancellation, but it deliberately withholds real approval until the authenticated
approval endpoint exists. The controlled demo's confirmation is a manual UI
baseline, not backend-enforced agent approval.

## 8. Persistence and recovery

Authoritative users, conversations, runs, proposals, approvals, tool attempts,
and outcomes belong in durable backend storage. Client memory is only temporary
view state. On restart, the service must recover completed results and pending
approval without guessing that an in-flight provider write failed.

Each provider attempt records started/confirmed/failed/uncertain state. A lost
response after a write remains uncertain until reconciled. The system does not
automatically retry writes or claim rollback of provider effects.

## 9. Vertical integrations

### HW3 Milestone 1: workflow configuration and partial failure (#84)

`WORKFLOW_IMPLEMENTATION=configured` selects real construction outside the
workflow. `CALENDAR_IMPLEMENTATION`, `STORAGE_IMPLEMENTATION`, and
`ISSUE_TRACKER_IMPLEMENTATION` select the supported packages. Configuration is
validated before the first write, and client cleanup is owned by composition.

The fixed order is Storage → Issue Tracker → Calendar. Failure stops downstream
steps and retains confirmed earlier outcomes. Controlled implementations can
force each step to fail; they verify orchestration behavior but do not count as
a genuine package swap.

### HW3 Milestone 1: Calendar composition entry point (issue #81)

The Calendar adapter consumes the tagged shared `CalendarService` contract and
reuses Team 2's Google provider boundary. Google request construction, response
translation, and credentials stay outside orchestration.

### Storage and Issue Tracker

The configured storage implementation is Team 3's tagged Dropbox package through
the shared Cloud Storage contract. The configured issue implementation is Team
4's tagged Trello package through the shared Issue Tracker contract. Package
versions and construction settings are in `pyproject.toml`, `STORAGE.md`, and
`ISSUE_TRACKER_HANDOFF.md`.

## 10. Model-versus-code decisions

The model may interpret intent, ask a clarification, and propose one of the
documented actions. Code owns schema validation, authorization, approval,
provider selection, sequencing, deadlines, cancellation, retry policy, state,
and response rendering. This boundary makes safety behavior deterministic and
testable even when model output is wrong or adversarial.

## 11. Failure behavior and reconciliation

The combined workflow identifies the failed step and reports earlier confirmed
steps separately from unattempted steps. Known provider rejections map to the
documented service error model. A timeout or lost response after a write is
non-retryable uncertainty, not a definite failure.

Users must not resubmit an uncertain workflow blindly. S2 and operator guidance
use retained references and authorized reads where available; otherwise they
state the specific manual provider check. Automatic compensation is out of scope
because it is another mutation requiring its own authorization and can also fail.

## 12. Security model

Security enforcement is server-side and deny-by-default:

- authenticated identity is required for user data and provider connections;
- object ownership is checked before returning data or dispatching a tool;
- approval is bound to user, run, proposal digest, and current revision;
- tool names and argument schemas are allowlisted;
- run time, model turns, and tool calls are bounded;
- cancellation is checked before and after external calls;
- secrets and private provider payloads are excluded from model context and
  telemetry;
- remote service URLs require TLS, and CSRF/session protections apply to the UI.

The readiness ledger requires explicit isolation, credential lifecycle,
approval-replay, prompt-injection, cancellation, and restart evidence before a
release is marked ready.

## 13. Major design decisions and tradeoffs

1. **One narrow product instead of general chat.** This reduces tool authority
   and creates observable success criteria. Revisit only after S1/S2 evidence.
2. **Shared package contracts, local adapters.** This prevents provider SDK
   leakage while accepting small construction adapters. Revisit if a shared
   contract cannot express required behavior.
3. **Exact approval before writes.** This adds persistence and UI work but makes
   user intent auditable and prevents stale approval. It is a launch gate.
4. **No automatic write retry or rollback.** This preserves ambiguity instead of
   causing duplicates. Revisit only with provider-backed idempotency/reconciliation.
5. **Interface remains a client.** It avoids duplicated policy and credentials;
   backend availability is therefore a product dependency.

## 14. Verification strategy

Automated tests use controlled verticals, transports, and model decisions for
deterministic contract, partial-failure, UI, security, and orchestration checks.
Opt-in tests cover real providers. Real-model evaluations, uncoached usability,
two-user isolation, deployment traceability, alert delivery, load/capacity,
backup restore, and recovery rehearsals require retained execution records.

Procedures do not count as proof. [READINESS.md](READINESS.md) is the canonical
ledger, and [evidence/README.md](evidence/README.md) defines the record format.

## 15. External and internal design reviews

### External design review — Faisal (Team 6)

Faisal reviewed the Milestone 1 integration boundary and identified package-swap
and provider compatibility constraints. The response retained configuration
outside workflow code, documented incompatible candidate packages, and did not
misrepresent controlled fakes as a genuine second implementation. Historical
details are in [DESIGN_HISTORY.md](DESIGN_HISTORY.md).

Milestone 2 review comments, reviewer identity, response, and resolving commit
must be retained in a concrete evidence record rather than represented by a bare
issue link.

## 16. Known limitations and future changes

- This branch does not yet contain the tracked agent-service implementation.
- Real user sign-in, provider-connection ownership, durable run/approval state,
  and authenticated execution are not integrated.
- The interface is a local single-test-account preview and has no completed
  uncoached usability record.
- Real-model repeated evaluations, measured iteration, two-user isolation,
  deployed end-to-end correlation, load, alert delivery, backup restoration,
  game day, cost measurement, and dated teardown evidence remain release gates.
- Historical HW2 evidence demonstrates earlier operational capabilities but
  does not prove the future Milestone 2 release.

## Compatibility anchors

### HW3 Milestone 2: Kickoff Handoff planning design

The product scope and technical plan are summarized in Sections 1–14 above.

### HW3 deployment and request trace (#85)

The Milestone 1 three-provider trace is preserved in
[DESIGN_HISTORY.md](DESIGN_HISTORY.md#hw3-deployment-and-request-trace-85).
Current Milestone 2 deployment evidence must be tied to the exact release in
[READINESS.md](READINESS.md).

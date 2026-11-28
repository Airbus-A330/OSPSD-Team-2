# HW3 Milestone 2 readiness ledger

This is the canonical entry point for Build and Ship readiness. `PASS` means the
linked retained artifact proves the claim. A procedure or historical HW2 record
does not make a future release pass.

Current planning revision: `5832532be3e0278ca456c7e2f638fdd032fbacb4`

## Documentation map

| Document | Purpose and reader | Role | Evidence support |
| --- | --- | --- | --- |
| [README](../README.md) | New developer setup and repository entry point | Instructions | Commands are checked by CI; not release evidence |
| [Product brief](HW3_MS2_PRODUCT_BRIEF.md) | Product, users, scenarios, measures, and assumptions for team/reviewers | Requirements | Links controlled assumption test; user discovery remains open |
| [Design](DESIGN.md) | Current architecture and decisions for engineers/reviewers | Design | Links readiness rather than embedding execution logs |
| [Interface guide](INTERFACE.md) | User/operator steps for the current client | Instructions and explicit limitations | Automated tests linked; human walkthrough pending |
| [Deployment](DEPLOYMENT.md) | Build/deploy/verify/teardown procedure for operators | Instructions | Exact-release record pending |
| [Delivery](DELIVERY.md) | CI/CD and rollback procedure for release operators | Instructions | Historical HW2 artifacts linked separately |
| [Observability](OBSERVABILITY.md) | Signal schema, dashboard, and verification procedure | Instructions plus labeled historical evidence | Local/historical artifacts linked with limitations |
| [Operations](OPERATIONS.md) | Ownership, costs, retention, and quick reference | Instructions and planning | Current cost/date fields explicitly pending |
| [Testing](TESTING.md) | Automated test boundaries and commands | Instructions | Test outputs must be retained for exact candidate |
| [Evidence index](evidence/README.md) | Record schema, privacy rules, and artifact locations | Evidence instructions | Existing artifacts are classified by scope |
| [Historical design](DESIGN_HISTORY.md) | Preserve milestone chronology and old review notes | Historical record | Not current architecture/readiness proof |
| [Historical deployment](DEPLOYMENT_HISTORY.md) | Preserve former mixed HW2 logs/checklist | Historical record | Not future Milestone 2 proof |

The structure is intentionally explicit: procedure documents explain how to run
an exercise, dated evidence records show what happened, and this ledger decides
whether the linked proof is sufficient.

## Current status

| Requirement | Status | Release/commit | Evidence |
| --- | --- | --- | --- |
| Product brief and scenarios | PASS | planning revision above | [Product brief](HW3_MS2_PRODUCT_BRIEF.md) |
| Milestone tracker | PASS | planning revision above | [Tracker](HW3_MS2_TRACKER.md) |
| Reader-first architecture/design | PASS | working tree pending review | [Design](DESIGN.md) |
| Manual interface controlled scenario | PASS — automated verification | current branch | `interface/tests/`; [interface guide](INTERFACE.md) |
| Uncoached interface walkthrough | MANUAL EVIDENCE REQUIRED | release candidate | No retained human record yet |
| Integrated agent service | PENDING | not present on this branch | Agent PR must be merged and reviewed |
| Deterministic agent tests | PENDING | exact integrated SHA required | Retain CI/test output after integration |
| Real-model evaluations (≥5 per key scenario) | MANUAL EVIDENCE REQUIRED | release candidate | No per-run records retained |
| Measured agent improvement | MANUAL EVIDENCE REQUIRED | release candidate | Before/change/fresh-rerun records absent |
| Authenticated exact approval | PENDING | not integrated | Interface intentionally withholds approval |
| Durable run/status/restart recovery | PENDING | not integrated | No authoritative persistence evidence |
| Two-user isolation and credential lifecycle | MANUAL EVIDENCE REQUIRED | release candidate | No retained two-user execution record |
| Shared vertical workflow | PASS — automated verification | current branch | Workflow and conformance suites; [Milestone 1 deployment](HW3_DEPLOYMENT.md) |
| Deployed product and exact release trace | PENDING + MANUAL EVIDENCE REQUIRED | future release | Delivery still triggers from `hw3-ms1-submission`; Milestone 2 run/Render record absent |
| Deployed end-to-end telemetry correlation | MANUAL EVIDENCE REQUIRED | future release | Existing capture is local or historical HW2 |
| Load/capacity test | MANUAL EVIDENCE REQUIRED | future release | No Milestone 2 load record |
| Delivered alert lifecycle | MANUAL EVIDENCE REQUIRED | future release | HW2 delivery screenshots/timestamps not retained |
| Failure game day and recovery | MANUAL EVIDENCE REQUIRED | future release | HW2 record lacks faulty digest/recovery run URL/timestamps |
| Backup restore into disposable environment | MANUAL EVIDENCE REQUIRED | future release | No execution record |
| Security/adversarial verification | MANUAL EVIDENCE REQUIRED | release candidate | Required matrix not retained |
| External-user onboarding | MANUAL EVIDENCE REQUIRED | release candidate | No uncoached outside-user record |
| Cost record | MANUAL EVIDENCE REQUIRED | release candidate | Model/telemetry/hosting usage not yet measured |
| Dated teardown plan | MANUAL EVIDENCE REQUIRED | before release | Owners must approve actual dates |
| Internal/external review record | MANUAL EVIDENCE REQUIRED | release candidate | Retain comments, responses, and resolving SHA |
| GitHub Release | PENDING | future exact SHA/tag | Release owner performs after all gates pass |

## Manual evidence required before submission

Save every record using [the evidence template](evidence/README.md).

### Real-model evaluation and iteration

- **Owner:** Alexander Freedman with an independent reviewer.
- **Run:** at least five fresh trials for S1 and five for S2, plus adversarial
  cases, using the exact release candidate and recorded model/prompt/tool versions.
- **Retain:** per-run inputs/state, allowed/prohibited actions, result, provider
  effects, approval outcome, latency, token usage/cost, cleanup, and failure reason.
- **Save under:** `docs/evidence/agent-evals/<date>/`.
- **Expected:** bounded execution, no unapproved writes, and a measured
  before/change/fresh-rerun comparison.

### Identity, approval, and security

- **Owners:** identity and durable-execution workstream owners.
- **Run:** two independent users; cross-user object/conversation/approval/
  connection attempts; missing/invalid/revoked credentials; sign-out replay;
  altered/replayed approval; prompt injection; unauthorized tool request;
  cancellation; restart with pending approval.
- **Retain:** expected and actual result, provider-call count, database state,
  test name/output, users' sanitized roles, and exact SHA.
- **Save under:** `docs/evidence/security/<date>/`.
- **Expected:** every prohibited action is denied before provider side effects.

### Uncoached usability and onboarding

- **Owner:** interface owner; tester must not be its implementer.
- **Run:** follow only the getting-started guide through manual S1, controlled
  failure, sign-in/connections, return login, and disconnect.
- **Retain:** timestamp, tester, instructions/version, task, questions/confusion,
  fixes and resolving commit, independent retest, and final outcome.
- **Save under:** `docs/evidence/usability/<date>/`.
- **Expected:** user completes the scenario and explains partial/uncertain results.

### Exact release, deployment, and telemetry

- **Owner:** release/infrastructure owner with an independent operator.
- **Run:** exact-commit CI and Delivery; second unchanged configuration apply;
  deployed S1/S2; one success, invalid input, and dependency failure.
- **Retain:** SHA, tag, CI URL, image digest, Render deployment ID/time, URL,
  health/smoke/cleanup, no-change output, run/request/trace IDs, correlated UI →
  agent → API → provider telemetry, and operator walkthrough notes.
- **Save under:** `docs/evidence/release/<date>/` and
  `docs/evidence/telemetry/<date>/`.
- **Expected:** exact artifact is healthy; the same deployed run is traceable
  without secrets or unbounded metric labels.

### Load, alert, game day, and restore

- **Owners:** readiness/reliability owner and independent responder.
- **Run:** documented load profile; actual alert threshold; bounded dependency or
  faulty-release exercise; rollback/recovery; database backup restore into a
  disposable environment.
- **Retain:** timestamps, load/sample size, firing and resolved notifications,
  redacted destination proof, fault SHA/image/deployment, recovery run/digest,
  post-recovery smoke, backup ID, restore start/end and data checks, cleanup,
  concise postmortem, owners and due dates.
- **Save under:** the matching `load/`, `alerts/`, `game-day/`, and
  `backup-restore/` dated directories.
- **Expected:** alerts are actually delivered, recovery uses the retained exact
  artifact, smoke passes, and restored data is verified.

### Cost and teardown

- **Owner:** release owner with each resource owner.
- **Run:** inspect provider billing/usage for the release period and agree on
  resource retention dates.
- **Retain:** plan, observed charge, measured usage/limits, date checked, owner,
  keep-through event, exact teardown/review date, and action.
- **Save in:** [OPERATIONS.md](OPERATIONS.md) with a dated supporting record under
  `docs/evidence/release/<date>/`.
- **Expected:** hosting, database, model, telemetry, and external-provider costs
  are explicit; every resource has a concrete date.

## Release decision

The repository is **not yet ready for a Milestone 2 GitHub Release**. Planning,
the controlled interface path, and historical operational infrastructure are
available, but agent integration, identity/approval/persistence, and the manual
release evidence above remain open. The release owner must replace each pending
row with a link to an actual retained artifact rather than changing status from
procedure alone.

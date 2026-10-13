# Team Agreement

This agreement defines how OSPSD Team 2 coordinates work on the Calendar
Service. It applies to every team member listed in the
[README](../README.md#team-members).

Repository-wide engineering standards remain canonical in
[AGENTS.md](../AGENTS.md). This document focuses on collaboration, ownership,
review, and release practices.

## Shared Expectations

- Treat teammates respectfully and assume good intent.
- Make progress visible through GitHub issues and pull requests.
- Ask questions early when a requirement, contract, or provider behavior is
  unclear.
- Raise schedule, access, or workload problems before they threaten a milestone.
- Understand and take responsibility for submitted work.
- Keep credentials, tokens, personal data, and other secrets out of the
  repository and team messages.

## Communication and Availability

GitHub is the source of truth for work that affects the repository:

- Issues record scope, acceptance criteria, ownership, dependencies, and blockers.
- Pull requests record implementation discussion, review, and verification.
- `docs/DECISIONS.md` records technical decisions that need a durable explanation.
- The team's group chat is used for quick coordination, meeting arrangements, and
  time-sensitive notices.
- Course Slack is used when staff clarification is needed or when an answer would
  benefit other teams.

Members should:

- share known periods of limited availability as soon as practical;
- acknowledge direct questions within 24 hours on weekdays and 36 hours on
  weekends;
- acknowledge review requests within 24 hours and aim to complete a focused
  review within 48 hours;
- tell the team when they cannot meet an agreed deadline so work can be adjusted.

These are coordination targets, not expectations that members remain constantly
online. Classes, work, health, and personal obligations take priority when they
are communicated promptly.

## Planning and Work Ownership

Work begins with a GitHub issue containing a clear outcome and acceptance
criteria. Before implementation, the team confirms any shared public contract
used by multiple issues.

Each substantial issue should identify:

- one primary owner;
- an expected deliverable;
- a reviewer other than the owner;
- known dependencies;
- a rough size or expected completion window.

To limit work in progress, each member should normally own no more than one
implementation issue at a time. A second item is reasonable for review,
documentation, or an agreed blocker workaround. New work should not displace an
unfinished higher-priority issue without team agreement.

The issue owner is responsible for keeping its status and blockers current. Work
that cannot fit in the current milestone is returned to the backlog with its
remaining scope documented rather than silently carried forward.

## Contracts and Technical Decisions

Public API and shared domain contracts must be agreed upon before dependent work
is divided. The canonical public contract is
[CONTRACT.md](CONTRACT.md).

For ordinary implementation choices, seek agreement among the affected
contributors. For a decision with broader impact:

1. describe the decision and realistic alternatives;
2. gather input from affected teammates;
3. prefer consensus;
4. if consensus is not practical, use a majority decision among available team
   members;
5. ask course staff when the disagreement depends on an ambiguous assignment
   requirement.

Significant decisions and trade-offs are recorded in
[DECISIONS.md](DECISIONS.md). A decision may be revisited when new requirements
or evidence invalidate its assumptions.

## Development Workflow

1. Select a ready issue and confirm its owner, scope, dependencies, and reviewer.
2. Create a focused branch named with the issue number and a short description.
3. Read the relevant contracts and documentation before editing.
4. Implement the smallest change that satisfies the issue, including focused
   tests and necessary documentation.
5. Run relevant checks during development and `make check` before requesting
   final review when practical.
6. Open a pull request linked to the issue and complete the repository pull
   request template.
7. Respond to substantive review comments with a change or a reasoned
   explanation.
8. Merge only after required checks pass and the required human review is
   complete.
9. Confirm the linked issue and documentation accurately reflect the merged
   result.

Branches and commits should remain focused on one issue. Do not add unrelated
cleanup to a feature pull request. Avoid rewriting history on a shared branch
without coordinating with everyone using it.

## Review and Merge Requirements

Every substantive pull request requires at least one approving teammate who is
not the author. The reviewer checks:

- behavior against the issue and public contract;
- tests and meaningful edge cases;
- readability and architectural boundaries;
- documentation and configuration changes;
- dependency and security implications;
- absence of secrets and unrelated changes.

The required Build, Format, and Tests checks must pass before merge. Reviewers
label feedback clearly as a blocking issue, design concern, question, or optional
suggestion. A green CI result supports review but does not replace human judgment.

The pull request author owns the final merge unless the team assigns another
person. The author also confirms that resolved review comments and the final diff
were not invalidated by a late merge from `master`.

## Blockers, Absence, and Urgent Work

A blocked member posts the following on the issue or pull request:

- what is blocked;
- what has already been tried;
- what decision, access, or input is needed;
- who can help;
- whether other work can continue safely.

If a blocker is not acknowledged within one working day, raise it in the team
chat. Provider access, cost, or assignment ambiguity should be raised with course
staff early.

When an owner becomes unavailable, the team may reassign the issue after recording
the current state and remaining work. Urgent defects are triaged by impact to the
current milestone or release. The team may pause lower-priority work, but it does
not weaken required checks or silently expand the urgent issue's scope.

## Release Lifecycle

The team uses semantic versioning during this assignment:

- review releases use a prerelease version such as `v0.1.0-rc.1`;
- the final assignment release uses `v0.1.0`;
- corrections after a published release use a new version rather than moving an
  existing tag.

For each release, the team assigns a release coordinator who:

1. identifies the exact commit and confirms the intended scope;
2. verifies required CI checks and known limitations;
3. asks a teammate to test setup and one representative workflow from a fresh
   checkout;
4. prepares reviewed release notes covering user-visible changes, linked issues
   and pull requests, configuration changes, compatibility changes, and known
   limitations;
5. creates the annotated tag and GitHub Release only after verification;
6. records the verification evidence.

The review release is marked as a prerelease. A different teammate coordinates
the final release. After the review release, the team records one observation
about the process and any resulting adjustment.

If a release is defective, the coordinator documents the impact and whether users
should return to an earlier version or wait for a correction. The team preserves
the original tag, fixes the defect through the normal review process, and publishes
a new version. The recovery note identifies any state or configuration that a code
rollback would not restore.

## Resolving Team Concerns

Discuss disagreements using concrete behavior, evidence, requirements, and
trade-offs. Address the concern rather than the person. If direct discussion does
not resolve the issue, involve another teammate as a neutral facilitator. Course
staff may help with persistent technical, access, workload, or participation
problems. Sensitive concerns may be raised privately.

## Maintaining This Agreement

The agreement should change when experience shows that a rule is unclear or is
not helping the team. Proposed changes are discussed by the team and reviewed like
other documentation changes. Each member is responsible for reading the current
agreement and raising concerns they cannot follow.

# HW3 Milestone 2 implementation tracker

This repository tracker links the [product scenarios](HW3_MS2_PRODUCT_BRIEF.md#s1--set-up-a-kickoff)
to their owning issues. Status below is a November 23, 2026 snapshot of GitHub.
Issue owners update the linked issue as work changes and revise this tracker
when a milestone, blocker, dependency or scope changes. Nicolas maintains the
planning links and records consequential changes with a reason.

| Issue | Owner | Scenario or capability | Current status | Dependencies and gates | Verifiable outcome |
| --- | --- | --- | --- | --- | --- |
| [#93 Product and plan](https://github.com/Airbus-A330/OSPSD-Team-2/issues/93) | Nicolas Ollivier | S1, S2 | Open; local plan drafted | Teammate discovery and technical-owner alignment pending | Linked brief, assumption evidence, scoped tracker and updated design reviewed. |
| [#94 Interface](https://github.com/Airbus-A330/OSPSD-Team-2/issues/94) | Yasmin Hassoobh | S1, S2 | Open; [PR #100](https://github.com/Airbus-A330/OSPSD-Team-2/pull/100) | #93 scenarios; #95 agent and run status; #96 sign-in; #97 approval/results. Controlled adapters support independent UI work. | Uncoached teammate completes manual S1 and understands a controlled partial failure; pilot UI can reopen S2 with an owned run. |
| [#95 Agent service](https://github.com/Airbus-A330/OSPSD-Team-2/issues/95) | Alexander Freedman | S1, S2 | Open; [PR #99](https://github.com/Airbus-A330/OSPSD-Team-2/pull/99) | #93 scenarios; #96 verified identity context; #97 durable state and execution. Scripted model and controlled API support independent work. Live evaluation requires credentials. | Proposes S1, answers S2 from owned status, obeys budgets/cancellation, and records at least five real-model trials per scenario plus adversarial and before/after evidence. |
| [#96 Identity and connections](https://github.com/Airbus-A330/OSPSD-Team-2/issues/96) | Dorien Zhang | S1, S2; isolation | Open; implementation status unconfirmed | Real account registration and provider consent/scopes gate live verification. Coordinate identity and connection ownership with #94, #95 and #97. | Two independently authenticated accounts with separate connections cannot access each other's resources or run data. |
| [#97 Durable execution](https://github.com/Airbus-A330/OSPSD-Team-2/issues/97) | Maksym Yemelianenko | S1, S2; approval, cancellation and replay protection | Open; implementation status unconfirmed | Coordinate immutable action artifacts with #95 and verified identity with #96. Controlled identities and providers support independent tests. | Prove restart recovery, exact approval, atomic execution claim, zero replay, cancellation and preserved per-step outcomes. |
| [#98 Readiness and release](https://github.com/Airbus-A330/OSPSD-Team-2/issues/98) | Xingjian “Leon” Liu | S1, S2; launch readiness | Open; release evidence pending | Integrated #94–#97, live credentials, exact-commit CI, operational evidence and external review. | Record release/deployment traceability, scenario smoke tests, alert delivery and dependency-failure rehearsal with owned follow-ups. |

Build one thin S1 path through the interface, agent, identity, execution
and deployment before expanding coverage. Add S2 using the same durable
outcomes. Treat any guardrail failure or unverified identity/approval
boundary as a launch blocker. Review #99 and #100 against the chosen
scenarios and agree on shared integration seams before merging.

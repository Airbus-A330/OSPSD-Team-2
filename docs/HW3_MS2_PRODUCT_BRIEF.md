# Kickoff Handoff — HW3 Milestone 2 product brief

**Owner:** Nicolas Ollivier · **Selected:** November 23, 2026
**Build and Ship due:** December 2 · **Launch week:** December 2–6, 2026

This short requirements brief connects the user job, product scope and
launch measures to the [implementation tracker](HW3_MS2_TRACKER.md).

## User, problem and evidence

Kickoff Handoff serves leads of small student software teams who personally
coordinate project kickoffs and already use Google Calendar, Dropbox and
Trello. Their job is to leave the team with a scheduled meeting, a shared
agenda and a tracked follow-up, and to know which pieces actually landed.

Consider a course team lead who schedules Friday's kickoff, switches to
Dropbox to write the agenda, then creates a Trello follow-up. The card
request times out. The lead has to check three tools to find out what exists
and whether repeating the request could create a duplicate. This story
illustrates the problem to validate with users.

**Team experience.** Team 2 built a fixed kickoff with step-aware partial
failure. The [design and external integration review](DESIGN.md#hw3-milestone-1-workflow-configuration-and-partial-failure-84),
[deployed verification](HW3_DEPLOYMENT.md) and [Trello handoff](ISSUE_TRACKER_HANDOFF.md)
record the team's integration work. The retained observations establish that
the three operations can be composed and that an interrupted run can leave
partial effects. They establish technical feasibility for the team’s setup.

**User evidence.** The repository and planning issue contain no target-user
interviews or observed manual baselines. Whether teams outside Team 2 share
the problem is unknown. Nicolas will review the story with teammates and,
if available, ask three outside leads to describe their most recent kickoff,
where they lost time and how they checked ambiguous outcomes. Record recent
examples and link consented, sanitized notes here. Reconsider the segment if
leads cannot point to recent examples of the job.

## S1 — Set up a kickoff

- **Intent:** “Set up Friday's Alpha kickoff at 2 p.m. and track the follow-up.”
- **Information:** Project name, explicit start/end and time zone, connected
  Calendar, Dropbox path and agenda content, and Trello board/list and card
  title. Clarify missing or ambiguous values. Use the supported Calendar
  event fields and the Trello card title.
- **Proposal and approval:** Show the exact event title and time, file path
  and content, card title and each destination. The signed-in user approves
  that version, rejects it, or edits it and reviews a fresh version.
- **Provider effects:** Create one Dropbox agenda, one Trello card and one
  Google Calendar event, in that order. Report each outcome and its known
  reference. If a step fails, stop downstream execution and show what was
  saved, what needs checking and what was never attempted.
- **Observable success:** The three records exist once with the approved
  values, and the interface reports matching results. Rejection prevents
  execution. Cancellation stops dispatch of remaining steps.

## S2 — Check a previous kickoff

- **Intent:** “Did the Alpha kickoff finish? What still needs my attention?”
- **Information:** Signed-in account and owned run reference. Clarify if
  several owned runs match. Retrieve durable outcomes and known references.
- **Proposed action and approval:** Read the owned run and, where supported,
  check known references through authorized provider reads. No write approval
  is needed for these reads.
- **Provider effects:** Zero mutations. Preserve uncertainty when a reliable
  lookup is unavailable and identify the concrete manual check.
- **Observable success:** The lead can reopen the app and distinguish recorded
  success, independently verified results, failed, uncertain and unattempted
  steps. The response gives a next check for each unresolved effect.

## Scope

| Priority | Features and rationale |
| --- | --- |
| Must | S1 and S2; manual S1 through a real interface; bounded model-driven agent; verified sign-in, isolated provider connections, durable exact approvals and progress, cancellation, evaluations and readiness evidence. |
| Should | A shortcut to reopen the last kickoff. Cut it first and retain explicit run lookup. |
| Won’t | Delegated schedulers and enterprise administrators have cross-user permission and resource-management needs outside a student lead’s job. |
| Won’t | Calendar invitations, provider ACL changes and bidirectional sync add side effects or conflict handling outside the kickoff contract. |
| Won’t | General chat, cross-workspace search and unrelated Calendar, Dropbox or Trello CRUD dilute the kickoff and status workflows. |
| Won’t | Automatic rollback, resumed writes or speculative retries after uncertainty can compound provider effects. Compensation itself requires a separate approved mutation and is outside pilot scope. |

## Launch measures and guardrails

During December 2–6, count each initiated S1 run once. For S2, count the
first check of a given run per user session. Clarifying turns and repeated
clicks within an attempt count once. Include failures, refusals, cancellations
and abandonment in the denominator and report their counts. Exclude labeled
demos and controlled tests. Record scenario, timing and evidence status
without private content. Report counts, unique users and denominators
alongside rates. With fewer than five attempts for a scenario, report its
rate as inconclusive.

| Scenario | Launch outcome target | Guardrails |
| --- | --- | --- |
| S1 | At least 80% of initiated kickoffs reach confirmed three-record completion within five minutes of the first request. | Zero writes without matching approval and verified ownership, zero cross-user access, zero duplicate effects and zero automatic writes following uncertainty. |
| S2 | At least 90% of initiated checks return a correct per-step summary within 30 seconds, checked against durable outcomes and available provider evidence. | Zero provider mutations, zero other-user disclosure and zero uncertain effects presented as confirmed. |

A guardrail violation pauses write rollout pending triage. Count uncertain
effects separately. Compare launch outcomes with prelaunch evidence using
the same scenario definitions, with sample sizes and conditions reported.

## Ranked assumptions and experiment

1. **Critical — The execution path can preserve ambiguity and stop without
   redoing work.** A lost response may follow a committed write. If the
   application reported that as a definite failure or automatically repeated
   a step, the recovery design would need to change.
   - **Test, November 23:** Exercised the existing fault-injection tests through
     the workflow and HTTP boundary using controlled providers. Reproduce
     with `uv run --locked python -m pytest tests/test_project_kickoff_workflow.py -vv`.
     See the [test fixtures and assertions](../tests/test_project_kickoff_workflow.py).
   - **Observed:** 31 passed. All three lost-response cases recorded a
     committed effect and returned an uncertain, non-retryable result. In the
     same-path replay case the second request returned 409 at storage; the
     tracker was called once across both requests and Calendar received zero
     calls.
   - **Decision:** Persist each outcome and offer read-only status checks.
     Keep uncertainty visible. #97 must prevent replay independently of
     storage path conflicts. The test establishes application behavior with
     fakes. Pilot-account provider reconciliation still requires verification.
2. **High — Leads routinely do this job and prefer one review.** If the job is
   rare or leads prefer to act independently, revisit the target segment or
   proposal shape after discovery and an uncoached walkthrough.
3. **High — Pilot users can connect and reach all three destinations.**
   OAuth restrictions or inaccessible resources would prevent S1. Verify
   with independently provisioned test users before launch.
4. **Medium — Users understand unresolved steps.** Watch users identify the
   next check without coaching. Revise the status view if they infer failure
   from uncertainty or try to repeat writes.

## Open questions

| Question | Proposed owner | Target date |
| --- | --- | --- |
| Do student leads have recent examples of all three steps and value one review? | Nicolas Ollivier | Nov 25 |
| Which exact provider lookups are available under pilot credential scopes? | Dorien Zhang and Maksym Yemelianenko | Nov 26 |
| How will returning users find a run and see unresolved outcomes? | Yasmin Hassoobh and Alexander Freedman | Nov 26 |
| Which accounts can demonstrate isolation and give course staff access? | Xingjian Liu and Dorien Zhang | Nov 30 |

See the [submission index](HW3_MS2_SUBMISSION.md) for the evidence handoff.

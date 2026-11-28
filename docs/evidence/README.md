# Evidence records

This directory stores sanitized execution evidence. Procedures live in the
top-level docs; a procedure, test plan, or unchecked checklist is not evidence
that an execution occurred.

## Required record format

Every Milestone 2 execution record must contain:

```markdown
# <Evidence name>

Date/time: <ISO 8601 timestamp and timezone, or NOT RETAINED>
Performed by: <name(s)>
Commit: <full SHA, or NOT RETAINED>
Release/tag: <tag, or NOT APPLICABLE / NOT RETAINED>
Environment: <local / CI / Render / disposable / production>
Deployment ID: <ID, or NOT APPLICABLE / NOT RETAINED>
CI run: <URL/ID, or NOT APPLICABLE / NOT RETAINED>
Image: <immutable digest, or NOT APPLICABLE / NOT RETAINED>

## Purpose
<requirement verified>

## Procedure
<exact commands or steps>

## Expected
<expected result>

## Observed
<actual result>

## Artifacts
<repository-relative links to screenshots, logs, JSON, or output>

## Result
PASS / FAIL

## Limitations
<what this evidence does not prove>
```

Never infer or fabricate a missing value. Use `NOT RETAINED` and add the item to
[READINESS.md](../READINESS.md).

## Evidence map

| Area | Existing record | Scope |
| --- | --- | --- |
| Historical HW2 deployment | [`../DEPLOYMENT_HISTORY.md`](../DEPLOYMENT_HISTORY.md) | Historical mixed log; not Milestone 2 proof |
| Historical Delivery | [`delivery/`](delivery/README.md) | Known-good HW2 run and explicitly incomplete rollback artifacts |
| Local telemetry | [`telemetry-local/`](telemetry-local/README.md) | Local synthetic capture only |
| Historical hosted reliability | [`reliability-live/`](reliability-live/README.md) | HW2 API, Delivery, dashboard, and SLI evidence with stated limits |
| Local reliability | [`reliability-local/`](reliability-local/README.md) | Local synthetic evidence |
| Hosted-local telemetry | [`reliability-hosted-local/`](reliability-hosted-local/README.md) | Local OTLP capture using hosted entry point |

Create dated Milestone 2 records only when the corresponding execution occurs:

```text
docs/evidence/
  release/<date>/
  agent-evals/<date>/
  security/<date>/
  usability/<date>/
  load/<date>/
  alerts/<date>/
  telemetry/<date>/
  game-day/<date>/
  backup-restore/<date>/
  reviews/<date>/
```

Each record must exclude credentials, tokens, authorization headers, private
provider identifiers, full request/response bodies containing user content, and
unredacted personal contact details.

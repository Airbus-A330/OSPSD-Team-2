# Agent Service

The agent service is a separate FastAPI process that accepts natural-language
goals, calls a configured language model, validates model decisions, and uses
Team 2's API service for permitted application operations. It never imports or
constructs Google Calendar, Dropbox, or Trello implementations.

## Run locally

Start the existing API service on port 8000, then configure the agent process:

```bash
export OPENAI_API_KEY='<local secret>'
export AGENT_MODEL_PROVIDER='openai'
export AGENT_MODEL='<approved-model-version>'
export AGENT_API_BASE_URL='http://127.0.0.1:8000'
uv run --locked uvicorn agent_service.main:app --port 8001
```

PowerShell uses `$env:NAME='value'` for the same variables. Never commit the API
key or put it in an agent request, model context, trace, or evaluation result.

The interface submits a natural-language goal:

```bash
curl -X POST http://127.0.0.1:8001/agent/requests \
  -H 'Content-Type: application/json' \
  -d '{"goal":"Prepare the project kickoff and ask me before creating anything"}'
```

The response stops in one of these states:

- `completed` — read-only work or explanation finished;
- `needs_clarification` — a material choice requires the user;
- `approval_required` — an exact write proposal is ready, but nothing executed;
- `blocked` or `failed` — policy, API, or model behavior prevented progress;
- `limit_exhausted` — a deterministic step, time, token, or available-cost limit stopped work;
- `cancelled` — no further step may begin; completed external effects are not undone.

`GET /agent/runs/{run_id}` returns the durable run record without rerunning the
model. `POST /agent/runs/{run_id}/cancel` persists cancellation. Level 4's
authenticated approval/execution work must scope both routes to the verified
user before deployment to real users.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_MODEL_PROVIDER` | `openai` | Only `openai` is supported in real composition; CI injects `ScriptedModel` directly |
| `AGENT_MODEL` | none | Required exact model/version retained in every run and evaluation |
| `OPENAI_API_KEY` | none | Required secret for real model calls |
| `OPENAI_RESPONSES_URL` | OpenAI Responses endpoint | Optional HTTPS endpoint override |
| `AGENT_MODEL_TIMEOUT_SECONDS` | `20` | Timeout for one model call |
| `AGENT_API_BASE_URL` | `http://127.0.0.1:8000` | Team 2 API service; credentials in this URL are rejected |
| `AGENT_API_SERVICE_KEY` | none | Optional hosted API service key; never sent to the model |
| `AGENT_API_TIMEOUT_SECONDS` | `10` | Timeout for one API call |
| `AGENT_MAX_STEPS` | `8` | Model-decision budget, bounded from 1 to 32 |
| `AGENT_MAX_DURATION_SECONDS` | `30` | Whole-run elapsed-time budget, at most 300 seconds |
| `AGENT_MAX_TOKENS` | `20000` | Total reported-token budget |
| `AGENT_MAX_COST_USD` | none | Cost budget enforced only when the model provider reports cost |
| `AGENT_STATE_DATABASE` | `.agent-state/agent.sqlite3` | SQLite run/proposal state; ignored locally and replaceable through `RunStore` |

Configuration errors are sanitized. Health checks do not contact the model, API
service, or providers.

## Tool contracts

The registry is an explicit allowlist. Pydantic generates the exact argument and
result JSON schemas supplied to the model and rejects unknown fields. A model
cannot add an acting `user_id`; authenticated identity will come from Level 4's
trusted application credentials.

### `read_calendar_event`

- **Purpose:** read one known event by opaque ID.
- **Arguments:** `{ "event_id": "nonblank string" }`.
- **Result:** the shared four-field `Event`, bounded by the API response limit.
- **Precondition:** the identifier is already known and authorized by the API.
- **Effect:** one `GET /events/{event_id}` call to Team 2's API service.
- **Failure:** invalid arguments are rejected locally; API failures become
  sanitized structured observations. No provider SDK or credential enters the
  agent process.

### `propose_project_kickoff`

- **Purpose:** prepare one exact three-vertical kickoff change set.
- **Arguments:** the existing `ProjectKickoffRequest` (`event`,
  `document_path`, `document_content`, and `issue_title`).
- **Result:** a proposal containing the method, API target, exact changes,
  effects, random proposal ID, and SHA-256 digest over the canonical action.
- **Preconditions:** every material field is explicit and validates against the
  existing API request contract.
- **Effect:** no API or provider write. It stops at `approval_required`.
- **Failure:** malformed or model-added fields are rejected before API/provider
  use. Any changed field produces a different digest and requires new approval.

The later approval layer must store approval against the proposal ID and digest,
derive the acting user from verified credentials, and ask the API service to
execute. Conversational “yes” is not authorization. This issue intentionally
provides no endpoint that converts a proposal into a write.

## Loop and trust boundaries

The framework-independent loop performs one decision at a time:

1. build model context from the bounded goal, conversation, registered tools,
   and prior observations;
2. call the configured `ModelClient`;
3. validate the structured decision;
4. reject unknown tools or schema-invalid arguments;
5. dispatch registered reads through the API service, or construct a proposal;
6. mark tool output `untrusted_tool_data` before the next model call;
7. stop for completion, clarification, approval, policy, cancellation, failure,
   or a configured limit.

Application instructions, tool definitions, identity, approval, and limits are
not taken from retrieved content or model output. Provider credentials are never
included in model context. The trace records model version, calls, outcomes,
policy decisions, durations, stopping reason, and reported usage, but stores no
private chain-of-thought, model key, provider credentials, or raw authorization
headers.

SQLite persists the request, exact proposal/result, trace, and cancellation
state across process restarts. It does not provide per-user isolation by itself;
the shared application database and authentication workstream must replace or
scope this seam before launch.

## Deterministic tests and real-model evaluations

`ScriptedModel` implements the same `ModelClient` interface as
`OpenAIResponsesModel`. Normal CI covers malformed calls, unknown tools,
clarification, model/API failures, proposal-only writes, cancellation, limits,
restart persistence, and adversarial retrieved content without network or
credentials.

Two executable definitions currently accompany the only established product
workflow and its adversarial control:

- `project_kickoff_proposal` — must reach one exact three-vertical proposal and
  stop before execution;
- `adversarial_retrieved_content` — a controlled event title contains an
  unrelated write instruction; no proposal or write is permitted.

Run at least five opt-in real-model attempts with an explicit output path:

```bash
uv run --locked python -m scripts.evaluate_agent \
  project_kickoff_proposal \
  --attempts 5 \
  --output .agent-state/evaluations/kickoff.jsonl \
  --allow-model-calls
```

Records contain success/failure, duration, provider/model version, prompt
version, exact tool-definition digest, and reported usage. The command may incur
model cost and does not approve or execute provider writes. Add each product
scenario from the final brief before claiming complete evaluation coverage.

## Evidence status and limitation

The deterministic agent boundary and evaluation tooling are implemented and
tested. Real-model five-run results, a real-model adversarial run, a measured
before/after improvement, authenticated approval execution, and provider
read-back after approval require the corresponding credentials/integrated Level
4 work and are not claimed by this implementation.

One remaining design limitation is that SQLite is a single-process development
store. Its `RunStore` boundary is deliberately small so the authoritative shared
database can replace it without changing the loop.


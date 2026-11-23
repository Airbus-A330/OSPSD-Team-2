# Workspace getting started

The web interface lets you prepare a kickoff document, a follow-up issue, and a
calendar event, review their exact contents, and send one request to Team 2's
API. Kickoff is the **temporary manual baseline**, not a finalized Milestone 2
product scenario. The product owner will confirm the final wording and inputs.

## For the person using the interface

1. Ask the operator to start the interface, then open **http://127.0.0.1:8001**.
2. Check which environment the operator supplied. The current preview uses one
   designated test account; the controlled demo creates only synthetic records.
   **Real-user sign-in is not connected yet.** Do not enter provider credentials.
3. In **Project kickoff**, enter an event title, start/end times with UTC offsets,
   a document path, document text, and follow-up issue title. For example:
   - Start: `2030-01-15T10:00:00-05:00`
   - End: `2030-01-15T10:30:00-05:00`
   - Document path: `/projects/my-test-project/kickoff.md`
4. Select **Review changes**. No provider write happens during review. Check the
   complete document text, issue title, and event times. Select **Reject and edit**
   to change them, or **Confirm and create all three** to submit once.
5. While waiting, leave the page open. The backend executes document → issue →
   calendar. It does not stream step updates, so the interface says **awaiting
   backend confirmation** rather than guessing which step is running.
6. Read each result. Keep the returned document path/ID, issue ID, and event ID.
   Print the page if you need a copy. Client drafts/results expire after 30 minutes
   of inactivity or a restart; this is not a durable run-history service.

### If something goes wrong

- **Failed:** read the backend's message and the suggested correction. Inspect
  whether any step succeeded before beginning a new execution.
- **Partially succeeded:** earlier records still exist. Keep their references
  and ask the account owner to reconcile the incomplete steps. Nothing is rolled back.
- **Uncertain:** a write may have happened even though confirmation was lost.
  Do not submit again. Retain the original path and request details for the owner.
- **Document path already exists:** do not rename it merely to bypass the error.
  Ask the owner to compare its contents and earlier results first.
- **Access denied:** check access to Team 2's service and ask the owner to check
  the affected connection. The interface never needs a Google/Dropbox/Trello token.

Refreshing a result page does not repeat its POST. A consumed review cannot be
submitted again within the same client session. These are UI safeguards, not
backend idempotency or durable approval guarantees. A new run remains a new write.

### Assistant and account panels

In the normal client these panels explicitly say that integration is pending.
Once adapters are connected, the assistant can show context retrieval, proposals,
exact before/after changes, target, revision, and approve/reject/request-change
controls. A plain chat message is not an approval. The account panel can display
signed-in/out state, provider attention, reconnect and disconnect controls.

The controlled demo supplies **fake** agent/account responses to exercise these
screens. Its sign-in button does not authenticate a real user, and its proposal
buttons do not establish backend-enforced approval. Final sign-in instructions
must be updated when Dorien's account contract is integrated.

## Operator setup

Follow the repository [setup](../README.md#3-install-python-and-locked-dependencies),
then run `uv sync --locked`. Start Team 2's API separately using the existing
[configuration](HW3_DEPLOYMENT.md). To point the UI at that API:

```bash
export INTERFACE_API_URL=http://127.0.0.1:8000
make interface-run
```

For a remote Team 2 API use HTTPS and supply its **application access token** as
`INTERFACE_API_TOKEN` through the local process environment. Do not put it in a
URL, command history, source file, browser form, or screenshot. This is the
existing test-account API access mechanism, not a provider credential or user login.
The token stays in the Python client's outbound Authorization header.

| Setting | Behavior |
| --- | --- |
| `INTERFACE_API_URL` | Team 2 API origin/base path; default `http://127.0.0.1:8000`; remote URLs require HTTPS |
| `INTERFACE_API_TOKEN` | Optional application bearer token for the configured API; never returned to the browser |

`make interface-run` binds to loopback, port 8001, with access logging disabled.
This is a single-test-account preview. **Do not publicly deploy it** before
per-user authentication, backend approval enforcement, HTTPS/cookie configuration,
and durable run/reconciliation APIs are integrated. The API deployment and Docker
entry point are unchanged. The UI rejects non-local Host headers.

The Python web client owns HTTP requests and template rendering. The browser
script only updates waiting text and disables duplicate clicks; it contains no
API client. Because the service client is Python like the backend, a separately
generated TypeScript/OpenAPI client is not required. Integration tests exercise
the actual API schemas and route through HTTP. Jinja2 is an explicit runtime
dependency; httpx moves from the dev group to runtime at its existing version.

## Controlled demo and usability check

No provider credentials, real provider writes, or model calls are involved.
Start these in separate terminals from the repository root:

```bash
# Terminal 1: actual API routes with controlled providers
uv run --locked uvicorn interface.tests.demo:api --host 127.0.0.1 --port 8002 --no-access-log

# Terminal 2: UI pointed only at that local controlled API; fake agent/account panels
uv run --locked uvicorn interface.tests.demo:ui --host 127.0.0.1 --port 8001 --no-access-log
```

Open http://127.0.0.1:8001 and follow the user steps above. To demonstrate a partial
failure, stop Terminal 1 and restart it with:

```bash
INTERFACE_DEMO_FAILURE=calendar uv run --locked uvicorn interface.tests.demo:api --host 127.0.0.1 --port 8002 --no-access-log
```

The document and issue succeed synthetically, Calendar fails with `access_denied`,
and the UI preserves the earlier references. Add `INTERFACE_DEMO_UNCERTAIN=1`
to demonstrate an uncertain Calendar write. Stop both servers with Ctrl+C afterward.

Ask a teammate who did not implement this interface to use **only this page and
the interface**, without coaching. Have them:

1. Prepare a kickoff, identify exactly what will change, reject it, edit, review,
   and confirm; find all three resulting references.
2. Repeat with the controlled failure; explain what succeeded, what failed,
   and what they would safely do next.
3. Inspect a fake agent proposal and identify its target and exact revision;
   reject it or request a change. Confirm they understand the demo is synthetic.

Record the reviewer/date/commit, environment, task outcome, verbatim confusion,
severity, fix commit, and independent retest. Do not record secrets or private data.

| Evidence | Status |
| --- | --- |
| Automated forms → HTTP client → actual API with controlled providers | Covered by `interface/tests/test_web.py` |
| Automated proposal/account adapter interactions | Covered using explicit fakes; no real auth/agent endpoints |
| Browser visual inspection | Pending: computer-use permission was unavailable in the implementation environment |
| Uncoached teammate success/failure session | Pending; no teammate session or feedback is claimed |
| Observed usability issues and fixes | Pending the uncoached session; do not infer these from automated checks |
| Live provider/model execution through this UI | Not performed |

On 2026-11-23, an automated local HTTP smoke check also ran two separate uvicorn
processes (web client on 8001, controlled API on 8002). Native-form HTTP submissions
confirmed all three synthetic references on success. Restarting the controlled
API with a Calendar rejection produced partial success with the document/issue
references retained, `access_denied`, reconciliation guidance, and rejection of
a repeated confirmation. Both processes were stopped afterward. This was a
programmatic HTTP check, not a browser visual review or a human usability session.

## Integration handoff

- **Product owner:** kickoff labels/fields live in `interface/web.py` and its
  templates. Keep business validation/execution in the API when replacing the scenario.
- **Alexander / Maksym:** `AgentClient` in `interface/clients.py` is a provisional
  typed adapter, not invented HTTP endpoints. Implement `submit`, `refresh`, and
  `decide` against the agreed separate agent service. `decide` carries run ID,
  proposal ID, exact revision, and explicit decision. The backend must derive
  identity from verified credentials, enforce current revision/approval, persist
  state, and prevent replay. The UI never executes agent tools itself.
- **Dorien:** `AccountClient` reports status and handles sign-in/reconnect/disconnect.
  A factory supplies a separate adapter per browser session. Implement the actual
  authentication/redirect/callback flow and verified per-user API credentials when
  the contract lands. Do not treat the UI session identifier as an authenticated user.
- **Hosting owner:** integrate the UI only after these security dependencies land.
  Transient UI state is not database storage. Restart/expiry discards drafts, not
  authoritative runs; backend run lookup must replace that limitation for launch.

Backend contracts and enforcement remain the source of truth. No provider SDK,
database client, provider credentials, new workflow rule, or duplicated agent/auth
subsystem is introduced by the interface.

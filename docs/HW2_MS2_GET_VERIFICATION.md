# Shared GET integration verification

Verified by Xingjian Liu on 2026-11-04 at 15:03 EST, using local verification
tooling. This is observed evidence, not an illustrative expected response.

## Revision and scope

The run used the PR #60 branch based on
`e388150d6b99d886bc9ea74f0fd71658e86bb8ed`, with the accompanying shared-interface
adapter changes in the working tree. It did **not** verify the unmodified base
commit. Git blob IDs identify the exact changed runtime files used in the run:

| File | Git blob ID |
|---|---|
| `app/calendar_service.py` | `80b89eb017cffd681319f28580eb62d08f05ddad` |
| `app/api/routes.py` | `aebb50f59f420a777018793d983cddd1de691048` |
| `app/composition.py` | `b3fb21a8fa759a1285c1ed11b49f47c6bfb8eaad` |

The shared dependency was `v0.1.0-rc.1`, resolving to
`1c1cad7a0732ddb242a05400d8833d94e4422424`. The path exercised was:

```text
HTTP client -> local uvicorn -> FastAPI GET route -> CalendarService.get
-> CalendarServiceAdapter -> application get_event -> cache wrapper
-> GoogleCalendarProvider -> real Google Calendar
```

The server started with an empty process-local cache. No provider substitution
or mocked SDK was used in the live HTTP requests. An existing timed OSPSD test
event was located by a read-only SDK query; no events were created, changed,
or deleted. Private event data and credentials are omitted below.

## Observed results

`GET /events/<existing-test-event-id>` returned **200**:

```json
{
  "id": "[redacted]",
  "title": "[redacted]",
  "start": "[redacted]",
  "end": "[redacted]"
}
```

All four unredacted values were compared in memory with the real SDK response
and matched exactly. The placeholders above redact private values; they are
not timestamp examples or literal API output values.

`GET /events/<random-nonexistent-id>` returned **404**:

```json
{
  "error": {
    "code": "not_found",
    "message": "Event not found",
    "retryable": false
  }
}
```

The local server was stopped afterward. No calendar data required cleanup.

## Reproduce

1. Install the locked dependencies and configure existing Google credentials as
   described in [PROVIDER.md](PROVIDER.md). Keep credential files ignored.
2. Select an existing timed event in your authorized test calendar. Retain its
   ID privately and compare its title/start/end against Google Calendar.
3. Start a fresh server: `uv run --locked uvicorn app.main:app --host 127.0.0.1
   --port 8000 --no-access-log` (one command). A fresh process ensures a cold cache.
4. Request `GET http://127.0.0.1:8000/events/<test-event-id>` using a local HTTP
   client. Confirm 200 and the four shared fields against the provider values.
5. Repeat with a random, nonexistent Google-compatible identifier (for example,
   a new UUID's 32 lowercase hexadecimal characters). Confirm the 404 body above.
6. Stop the server. Do not commit private IDs, titles, timestamps, or credentials.

## Automated checks and limits

`make check` passed: Ruff format/lint, mypy, **603 tests**, byte compilation,
and application import. Ten new tests cover the adapter and shared GET boundary,
including two reused GET cases from the tagged conformance suite with controlled
SDK fixtures. The test run reported one upstream Starlette/AnyIO deprecation
warning, with no failures.

The live run establishes GET success and missing-event behavior through the real
provider. Permission errors, outages, empty titles, and invalid IDs are covered
by controlled tests; they were not induced on the live calendar. Full shared
create/replace/delete HTTP migration, complete conformance, and deployment are
still follow-up work. This record does not claim those are complete.

# Provider Integration

This document records facts and assumptions about the selected external provider.

Do not copy provider-specific behavior into `CONTRACT.md` unless it becomes part of our own public contract.

## Selected Provider

Google Calendar API v3, accessed through Google's Python client libraries.

## Official Documentation

- [Google Calendar Python quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python)
- [Google Calendar API scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Google OAuth security best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices)
- [Events: get](https://developers.google.com/workspace/calendar/api/v3/reference/events/get)
- [Events: list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
- [Events: insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
- [Events: update](https://developers.google.com/workspace/calendar/api/v3/reference/events/update)
- [Events: patch](https://developers.google.com/workspace/calendar/api/v3/reference/events/patch)
- [Events: delete](https://developers.google.com/workspace/calendar/api/v3/reference/events/delete)

## Authentication

Local development uses Google's OAuth 2.0 installed-application flow. The service
requests this event read/write scope:

```text
https://www.googleapis.com/auth/calendar.events
```

This scope permits reading and editing events without granting access to broader
calendar settings. Google documents it as an accepted scope for event insertion
and replacement. Existing read-only tokens must be replaced by authorizing again,
and the account must have write access to the configured test calendar.

### Local setup

1. Create or select a Google Cloud project and enable the Google Calendar API.
2. Configure the Google Auth consent screen. If the app is in testing mode, add
   each teammate's Google account as a test user.
3. Create an OAuth client with the **Desktop app** application type.
4. Download the client configuration and save it outside version control. By
   default, the code reads `credentials.json` from the repository root.
5. Install locked dependencies with `uv sync --locked`.
6. Run the manual verification command below. On first use, a browser opens for
   consent and the resulting authorization is stored in `token.json`.

Alternative locations can be supplied with these environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_CALENDAR_CREDENTIALS_FILE` | `credentials.json` | Downloaded desktop OAuth client configuration |
| `GOOGLE_CALENDAR_TOKEN_FILE` | `token.json` | Generated user access and refresh token data |
| `GOOGLE_CALENDAR_ID` | `primary` | Calendar used by the public event operation |

Both default files, `.env` files, and downloaded `client_secret*.json` files are
ignored by Git. Never commit or share these files. Store them securely and revoke
the authorization in the Google account when it is no longer needed.

If the requested scopes change, delete the local token file and authorize again.
Existing tokens created with the former read-only scope must therefore be deleted
and authorized again before testing write operations.

When an expired saved token has a refresh token, client construction refreshes it
before building the Calendar client. A refresh transport failure becomes the
shared provider failure and is rendered as HTTP 502 when construction occurs for
a request. Missing or malformed local credential files remain configuration
errors: correct the documented local setup rather than treating them as provider
outages.

### Manual authentication verification

From the repository root, run:

```bash
uv run --locked python -c "from app.google_calendar import build_google_calendar_client; client = build_google_calendar_client(); client.events().list(calendarId='primary', maxResults=1).execute(); print('Authentication successful')"
```

The first run should open Google's consent flow. A successful request prints the
confirmation message and creates the configured token file. This command
contacts the real provider and is intentionally excluded from automated tests and
CI.

### End-to-end event verification

After completing authentication, verify the full HTTP path against a titled,
timed event in the configured test calendar:

1. Set `GOOGLE_CALENDAR_ID` if the event is not in the authenticated account's
   primary calendar.
2. Find a usable Google event ID:

   ```bash
   uv run --locked python -c "import os; from app.google_calendar import build_google_calendar_client; c=build_google_calendar_client(); events=c.events().list(calendarId=os.getenv('GOOGLE_CALENDAR_ID', 'primary'), maxResults=10, singleEvents=True).execute().get('items', []); print(*[(e.get('id'), e.get('summary')) for e in events], sep='\\n')"
   ```

3. Start the service in one terminal:

   ```bash
   uv run --locked uvicorn app.main:app --reload
   ```

4. Request the selected event in another terminal:

   ```bash
   curl http://127.0.0.1:8000/events/<EVENT_ID>
   ```

A successful response has HTTP status 200 and exactly the `id`, `title`, `start`,
and `end` fields from `CONTRACT.md`. Two teammates must run these steps with the
team's test calendar and record their names, dates, and sanitized outcomes in the
pull request without posting event identifiers, private calendar data,
credentials, or tokens.

### End-to-end event creation verification

After authentication and service startup, create a disposable timed event:

```bash
curl -i -X POST http://127.0.0.1:8000/events \
  -H "Content-Type: application/json" \
  -d '{"title":"OSPSD Create Verification","start":"2026-10-22T10:00:00-04:00","end":"2026-10-22T10:30:00-04:00"}'
```

On Windows PowerShell, run the command with `curl.exe`. The expected result is
HTTP 201 and an `Event` containing a provider-generated `id` plus the created
title, start, and end values. Copy that ID and verify the event through
`GET /events/<EVENT_ID>` and in the configured Google Calendar.

Clean up the disposable event after verification:

```bash
uv run --locked python -c "import os; from app.google_calendar import build_google_calendar_client; c=build_google_calendar_client(); c.events().delete(calendarId=os.getenv('GOOGLE_CALENDAR_ID', 'primary'), eventId='<EVENT_ID>').execute(); c.close(); print('Cleanup successful')"
```

Record the request, expected result, observed status/body, provider observation,
and cleanup result without recording credentials or private calendar data.

### Cleanup

Delete every disposable event created during verification. Stop the local service
when verification is complete. To remove local authorization, delete the
configured token file and revoke the app's access from the Google account; do not
commit or share either credential file.

### Final public-operation verification

Team 2 completed a real-provider verification of all six public operations on
2026-10-20 using the production FastAPI paths, configured Google test calendar,
and disposable attendee-free events. The observed results matched the public
contract:

| Public operation | Observed result and provider effect |
|---|---|
| `GET /events/{event_id}` | 200 with exactly `id`, `title`, `start`, and `end`; values matched Google Calendar |
| `GET /events?limit=2` | 200 with a bounded array of public Events; a returned ID was confirmed through GET |
| `POST /events` | 201 with a provider-generated ID; the event appeared in Google Calendar |
| `PUT /events/{event_id}` | 200; title, start, and end were replaced in the response, subsequent GET, and Google Calendar |
| `PATCH /events/{event_id}` | 200; supplied values changed while omitted values remained unchanged in GET and Google Calendar |
| `DELETE /events/{event_id}` | 204 with no body; repeated DELETE and subsequent GET returned the documented 404 envelope |

Invalid local input was also confirmed to return the documented 400 response
without a provider write. Disposable events were deleted and the local service
was stopped. Credentials, tokens, private calendar data, and event identifiers
are intentionally excluded from this record. The final release process separately
records the exact tagged revision and its CI results.

## Provider Operations

| Service behavior | Provider API/SDK operation | Notes |
|---|---|---|
| Construct an authenticated client | `googleapiclient.discovery.build("calendar", "v3", ...)` | Authentication setup documented above |
| Retrieve one event | `client.events().get(calendarId=calendar_id, eventId=event_id).execute()` | Reads external state without modifying it |
| List events | `client.events().list(calendarId=calendar_id, maxResults=limit, singleEvents=True).execute()` | One read-only page; returns at most the requested number of domain Events |
| Create one event | `client.events().insert(calendarId=calendar_id, body=...).execute()` | Creates a timed event and returns the provider-generated ID |
| Replace one event | Fresh `events.get`, then `events.update` | Rejects missing/cancelled state before replacing service-editable values |
| Partially update one event | Fresh `events.get`, then `events.patch` | Rejects missing/cancelled state; sends only supplied editable fields |
| Delete one event | `client.events().delete(calendarId=calendar_id, eventId=event_id).execute()` | Deletes the identified event; returns no domain value or SDK response |

Provider operation helpers receive an already configured client, which can be
built with `build_google_calendar_client`. The caller owns the client lifecycle.

`app.google_calendar.get_event(client, calendar_id=..., event_id=...)` requires
both identifiers and passes them unchanged to the SDK:

- `calendar_id` identifies the calendar containing the event. Callers may
  explicitly pass `primary` for the authenticated user's primary calendar or a
  specific calendar ID. The function does not choose a calendar or read configuration.
- `event_id` is the Google event resource's `id`, not its `iCalUID`, title, or
  browser URL. Lookup by `iCalUID` uses `events.list`, outside the supported
  retrieval contract.

### Domain-facing Google provider

`app.google_calendar.GoogleCalendarProvider` implements all six documented event
operation signatures from
[`ARCHITECTURE.md`](ARCHITECTURE.md#provider-boundary).
Supply an already configured client and an explicit calendar ID:

```python
from app.google_calendar import GoogleCalendarProvider

provider = GoogleCalendarProvider(client, calendar_id="primary")
event = provider.get_event(event_id)
```

The caller owns client construction, authentication, and lifecycle. The
constructor stores the client and calendar ID without performing I/O. Each
operation uses provider-specific request and translation functions within this
module, returning the domain `Event` rather than a raw Google dictionary.
Google failures are translated into the service errors from `app.errors`
before they leave this module. A 404 becomes `NotFoundError`. A 403 becomes
`PermissionDeniedError`, except when Google's machine-readable error reason
(`error.errors[].reason`) reports a quota or rate limit — `quotaExceeded`,
`rateLimitExceeded`, or `userRateLimitExceeded` — because Google also returns
403 for those provider limits; they become `ProviderFailureError`, as do 429
and any other status. Transport failures while executing the request
(`httplib2.HttpLib2Error`, Google authentication `TransportError`, socket
timeouts, and connection errors) also become `ProviderFailureError`. Only the
status and machine-readable reasons are interpreted; Google error messages
never cross the provider boundary, and the raw provider exception is not
retained as the translated error's cause. The low-level field mapper rejects
unsupported response shapes,
such as all-day events; the domain-facing provider translates those mapping
failures into `ProviderFailureError` before they cross the provider boundary.

`app.main.get_event_provider` is the composition point. For each HTTP request, it
builds the configured Google client, supplies it with `GOOGLE_CALENDAR_ID`
(defaulting to `primary`) to `GoogleCalendarProvider`, and closes the client after
the request. This request-scoped ownership avoids sharing the client's
non-thread-safe HTTP transport across worker threads. Application logic uses only
the provider-independent `EventProvider` contract in `app.providers`.

### List events verification

`GoogleCalendarProvider.list_events(limit)` uses the configured calendar and
existing read scope. Google documents `maxResults` as a per-page maximum: pages
can be short or empty even when a `nextPageToken` exists. This service deliberately
returns only the first page and does not expose or follow that token. Recurrences
are expanded with `singleEvents=True`; no chronological ordering is requested.
Each result uses the existing four-field mapping below. Unsupported untitled or
all-day events cause a shared provider failure, not a partial/silently filtered
response. HTTP/transport failures use the existing Google error classifier.

After completing local OAuth setup and starting the service as documented above:

```bash
curl -i 'http://127.0.0.1:8000/events?limit=2'
curl -i 'http://127.0.0.1:8000/events?limit=0'
```

Expected: the first request returns 200 with zero to two four-field Events whose
values match the configured test calendar; verify a returned ID with
`GET /events/<EVENT_ID>`. The second returns 400 `invalid_input` with message
`Invalid event limit`, without a provider request. Use a test calendar containing
titled, timed events; listing is read-only and needs no resource cleanup. Stop the
server afterward. Record the date, commit, expected/observed results, and comparison
without posting credentials or private calendar data.

**REAL PROVIDER VERIFICATION PERFORMED on 2026-10-20.** Team verification used
the production FastAPI path and configured Google test calendar. A bounded list
request returned HTTP 200 with no more than the requested number of four-field
events, and a returned identifier was confirmed through GET. `limit=0` returned
the documented HTTP 400 response before provider setup. Listing changed no
calendar state, so no resource cleanup was required.

## Field Mapping

`GoogleCalendarProvider` translates the raw Google event before returning across
its domain-facing boundary. The mapping is:

| Provider field | Domain field | Notes |
|---|---|---|
| `id` | `id` | Preserve the event ID; do not substitute `iCalUID` |
| `summary` | `title` | Google names the event title `summary` |
| `start.dateTime` | `start` | Preserve the timestamp string, including its offset |
| `end.dateTime` | `end` | Preserve the timestamp string, including its offset |

`app.google_calendar.translate_google_event` returns the `Event` model from
`app.models`. It selects only these four fields. Other provider fields, including
`kind`, `etag`, organizer data, and nested `timeZone`, are not exposed.

For creation, the request mapping is deliberately limited:

| Domain request field | Google request field |
|---|---|
| `title` | `summary` |
| `start` | `start.dateTime` |
| `end` | `end.dateTime` |

Google generates the event `id`. The complete Google result is translated back
through the same four-field `Event` mapping used by retrieval.

These mappings implement the four public fields approved in `CONTRACT.md`. The
following provider assumptions remain relevant to that contract:

- The mapper input is a titled, timed event with `id`, `summary`,
  `start.dateTime`, and `end.dateTime`. Missing required fields are rejected; no
  placeholder title, identifier, or timestamp is invented. The domain-facing
  provider exposes this as the shared provider failure.
- The low-level mapper preserves timestamp strings. Before a domain event leaves
  the provider, its title and times are checked against the existing nonblank,
  offset-aware, increasing-interval rules used by `EventReplacement`. Values are
  not trimmed or normalized. Unsupported success data becomes `ProviderFailureError`.
- Google's all-day events use `start.date` and `end.date` instead of `dateTime`.
  They are unsupported and become the shared provider failure; dates are not
  silently converted to midnight timestamps.
- Google's end boundary is exclusive. It is copied unchanged; this mapper does
  not adjust the duration or define new public interval semantics.
- GET, PUT, and PATCH treat `status=cancelled` as `NotFoundError` before reading
  fields; sparse tombstones cannot become successful Events. Cancelled records in
  LIST/POST responses are unsupported provider data. GET/PUT/PATCH also reject a
  returned ID different from the requested ID, without imposing Google ID syntax.
- Non-object SDK results, malformed list items, missing fields, and invalid event
  values become `ProviderFailureError`, not unhandled shape errors. A LIST object
  with no `items` remains a valid empty page. DELETE does not require a response body.

Provider field names and representations follow the official
[Events resource reference](https://developers.google.com/workspace/calendar/api/v3/reference/events).
The fixtures are representative synthetic responses, not real-account captures.
Translation is tested without SDK calls, credentials, or network access in the
default suite and was also exercised by the end-to-end verification recorded
below.

## Provider Limitations

- The installed-application OAuth flow requires an interactive browser on first
  authorization.
- Tokens created before the event read/write scope was adopted must be deleted
  and reauthorized before create, update, or delete operations can succeed.
- Local token storage is suitable for development only; a production deployment
  would require an appropriate secure credential store and authentication design.

The low-level provider operation helpers propagate SDK errors unchanged; the
domain-facing provider translates Google HTTP error responses into the service errors
defined in [CONTRACT.md](CONTRACT.md). Neither maps failures to HTTP status
codes directly, hides failures behind empty results, or adds retries,
pagination, or other operations.

## Verified Assumptions

### PUT replacement implementation and manual verification

`GoogleCalendarProvider.replace_event` first makes one fresh `events.get` call,
then one `events.update(calendarId=..., eventId=..., body=...).execute()` call
only if the resource exists and is active. The preflight bypasses the application
cache. A missing/cancelled resource causes no update attempt.
It sends `summary`, `start.dateTime`, and `end.dateTime`, then translates the
result into the four-field Event. It uses the shared Google HTTP/transport error
translation and performs no retries. Client ownership remains request-scoped.
Google's [events.update documentation](https://developers.google.com/workspace/calendar/api/v3/reference/events/update)
specifies full resource replacement, not patch semantics. Provider-only editable
fields omitted from the update are not preserved by this service; use a disposable,
non-recurring, titled timed event with no guests for verification.

**REAL PROVIDER VERIFICATION PERFORMED on 2026-10-20.** Team verification created
a disposable titled timed event through the public API, replaced all three
editable values through PUT, and observed HTTP 200 with the resulting four-field
Event. GET and the configured Google test calendar showed the same replacement
title and interval. The disposable event was deleted after verification; no
credentials, private calendar data, or event identifiers are recorded here.

A failed write can have applied remotely; retrieve the event before deciding
whether to repeat a request. Do not interpret 502 as proof of unchanged state.

- Google's official Python quickstart uses desktop OAuth credentials, caches user
  authorization in a local token file, refreshes expired credentials when a
  refresh token is available, and constructs Calendar API v3 with
  `googleapiclient.discovery.build`.
- Unit tests verify the same client-construction branches without real credentials
  or network access.

Credential-free tests with a mocked Google client verify the `events.get` inputs,
request execution, unchanged result data, and propagation of a Google HTTP error.
HTTP integration tests verify provider retrieval, translation, and response
serialization with the Google SDK boundary controlled.

On October 6, 2026, Airbus-A330 and LeonLiu0204 reported successful end-to-end
verification against the real provider.

On October 12, 2026, a separate live verification was run locally for LeonLiu0204
using desktop OAuth with the read-only event scope. A disposable,
attendee-free timed event was retrieved through `GoogleCalendarProvider`; the
returned `Event` contained exactly `id`, `title`, `start`, and `end`, and its
timestamp strings were preserved. The event identifier and calendar data are
intentionally omitted from this record.

This verifies the concrete provider independently of HTTP wiring. The
credential-free HTTP integration test separately verifies application
substitution with a controlled provider. Credentials and tokens remain in
ignored local files and are not part of this evidence.

## Delete verification

Xingjian's `GoogleCalendarProvider.delete_event` calls
[`events.delete`](https://developers.google.com/workspace/calendar/api/v3/reference/events/delete)
once with the configured `calendarId` and unchanged `eventId`. It discards the
empty SDK result and needs the existing `calendar.events` write scope.
HTTP 404 maps to `NotFoundError`; for this operation only, Google's documented
[`410 deleted`](https://developers.google.com/workspace/calendar/api/guides/errors#410_gone)
also maps to `NotFoundError`. Unrelated 410 reasons remain provider failures.
Other errors reuse the shared translation, including 403 quota errors as
`ProviderFailureError`, not access denial.

**REAL PROVIDER VERIFICATION PERFORMED on 2026-10-20** for DELETE. The local
read-only authorization was replaced through explicit Google consent for the
existing event read/write scope. Verification used the production app served by
Uvicorn on loopback, real Google clients, and a newly created attendee-free event.

| Step | Expected | Observed |
|---|---|---|
| POST disposable event | 201 with generated ID | 201 |
| GET before deletion | 200 | 200 |
| DELETE event | 204, empty body | 204, zero body bytes |
| Repeat DELETE | 404, fixed missing-event envelope | Matched |
| GET after deletion | 404, fixed missing-event envelope | Matched after tombstone fix |
| Inspect same Google event | No active event | `status=cancelled` |

The first live run exposed a retrieval defect: Google's cancelled record retained
event fields and was returned as HTTP 200. The adapter now checks that status
before translating the record. Two controlled regression cases and a second
live run confirmed the correction. Both disposable events used across the two
runs were deleted; local verification servers were stopped. No attendees,
credentials, private event content, or event identifiers are included here.

Real permission-denial and transport/provider failures were not induced.
Their public behavior is verified only by the controlled tests.

To reproduce:

1. Authorize the documented event read/write scope using a test account/calendar.
   Keep all credential and token files ignored by Git.
2. Start the service using the README command. Create a fresh disposable event
   through `POST /events` using the example above. Do not add attendees.
3. Record its returned ID locally. Confirm the event exists in Google Calendar.
4. Run the DELETE example in
   [CONTRACT.md](CONTRACT.md#delete-event--xingjian-liu-operation-6).
   Expect 204 and zero response-body bytes.
5. Repeat DELETE for that ID. Expect 404 and
   `{"error":{"code":"not_found","message":"Event not found"}}`.
   GET the same ID and expect that same 404 envelope. Confirm the event is absent
   from the active Google Calendar view. Google may retain a cancelled tombstone,
   so this is not a physical-erasure guarantee.
6. If verification stops early, remove only that disposable event manually.
   Record expected/observed statuses and cleanup without tokens or private data.

A failed response does not prove that deletion failed remotely. Inspect current
state before any manual retry. The adapter does not automatically retry.

## Partial update verification

`GoogleCalendarProvider.patch_event` uses
[Google events.patch](https://developers.google.com/workspace/calendar/api/v3/reference/events/patch).
Only supplied fields are mapped: `title` to `summary`, `start` to `start.dateTime`,
and `end` to `end.dateTime`. Google preserves unspecified fields. Each PATCH uses
one fresh SDK GET preflight and at most one SDK write. For a one-sided time
change the application also reads the domain event (possibly cached); the adapter
rechecks the combined interval against the fresh preflight before writing.
Thus a successful one-sided PATCH uses two SDK calls on an application cache hit,
or three on a miss. Other PATCH requests use two SDK calls.
Google charges three quota units for the PATCH write itself. The existing `calendar.events` scope
and request-scoped client lifecycle are reused. Failures use the shared Google
classifier. No automatic retry or concurrency guarantee is added.

**REAL PROVIDER VERIFICATION PERFORMED on 2026-10-20.** Team verification created
a disposable event through POST, patched its title through the public API, and
observed HTTP 200. GET and Google Calendar confirmed that the title changed while
the omitted start and end values were preserved. A second PATCH changed only the
end time and preserved the title and start. The disposable event was deleted and
the local service was stopped; no credentials, private calendar data, or event
identifier are included here.

A failed write may have taken effect. Inspect current state after an ambiguous
failure before retrying or cleaning up; do not infer rollback from an error response.

### Deleted-resource preflight tradeoff (#57)

PUT/PATCH intentionally do not restore a tombstone observed by their fresh
preflight. A cancelled write response is also a missing-resource failure, never
HTTP 200. Preflight and mutation are separate requests: an external deletion or
edit between them can still race the write. There are no ETags, retries, locks,
or atomic conditional-update guarantees.

A stale application cache can reject a one-sided PATCH that a newer external
interval would permit. This remains within the documented external-change cache
staleness window; retry after expiry or supply both time boundaries. The fresh
provider check prevents the opposite case from sending an invalid combined
interval based solely on an old cached boundary. Revisit conditional updates if
atomic protection against concurrent external edits becomes required.

Google 404s retain the existing shared `not_found` mapping. On LIST/POST this can
mean the configured calendar is missing/inaccessible rather than an individual
event. The fixed public text remains `Event not found`; no provider details or
new error categories are exposed. This wording limitation is not proof of an
individual event's absence on collection operations.

### Issue #57 live verification — 2026-10-21

**Actually run locally on branch #57:** FastAPI `TestClient` invoked the normal
HTTP application with the real request-scoped Google provider and shared cache;
there were no dependency overrides or SDK mocks. Existing saved authorization
was refreshed. Two new, non-recurring, attendee-free disposable events were used.

| Request / observation | Expected | Observed |
| --- | --- | --- |
| POST A; GET A | 201; 200 | 201; 200 |
| DELETE A | 204 with empty body | 204, zero response bytes |
| GET A after delete; repeat DELETE A | 404; 404 | 404; 404 |
| PUT A after delete | 404 `not_found` | 404 with the fixed error envelope |
| Direct Google check after PUT | Still deleted/cancelled | Confirmed inactive |
| PATCH A: title, both times, start only, end only | 404 each | 404 each |
| Direct Google check after PATCH | Still deleted/cancelled | Confirmed inactive |
| POST B; normal full PUT B | 201; 200 | 201; 200 |
| Fresh GET and direct Google read | Replacement persisted | Title/time replacement confirmed |
| Title-only PATCH B; end-only PATCH B | 200; 200 | 200; 200 |
| Fresh GET and direct Google read | Omitted fields preserved | Title, start and updated end confirmed |
| LIST with limit=1 | 200, at most one four-field Event | Matched |
| DELETE B cleanup; direct Google read | 204; inactive | Matched |

Both owned test events were confirmed inactive in cleanup. No private event IDs,
provider payloads, authorization codes, or token contents are recorded here.
These observations verify the local changes, not a pushed commit, release tag,
or a guarantee against external edits racing the preflight.

To repeat before a release: POST a disposable event; GET 200; DELETE 204; GET 404;
repeat DELETE 404; PUT the same ID and require 404; verify it remains cancelled in
Google; PATCH it and require 404; verify cancellation again. Create a second
event; PUT 200; GET the replacement; PATCH 200; GET the partial update with omitted
fields preserved; DELETE 204 for cleanup. Use only test-owned events without guests.

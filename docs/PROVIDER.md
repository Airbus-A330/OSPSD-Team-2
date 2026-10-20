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
team's test calendar and record their names, dates, event IDs, and successful
responses in the pull request without posting credentials or tokens.

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

## Provider Operations

| Service behavior | Provider API/SDK operation | Notes |
|---|---|---|
| Construct an authenticated client | `googleapiclient.discovery.build("calendar", "v3", ...)` | Authentication setup documented above |
| Retrieve one event | `client.events().get(calendarId=calendar_id, eventId=event_id).execute()` | Reads external state without modifying it |
| List events | `client.events().list(calendarId=calendar_id, maxResults=limit, singleEvents=True).execute()` | One read-only page; returns at most the requested number of domain Events |
| Create one event | `client.events().insert(calendarId=calendar_id, body=...).execute()` | Creates a timed event and returns the provider-generated ID |

Provider operation helpers receive an already configured client, which can be
built with `build_google_calendar_client`. The caller owns the client lifecycle.

`app.google_calendar.get_event(client, calendar_id=..., event_id=...)` requires
both identifiers and passes them unchanged to the SDK:

- `calendar_id` identifies the calendar containing the event. Callers may
  explicitly pass `primary` for the authenticated user's primary calendar or a
  specific calendar ID. The function does not choose a calendar or read configuration.
- `event_id` is the Google event resource's `id`, not its `iCalUID`, title, or
  browser URL. Lookup by `iCalUID` uses `events.list`, outside this issue.

### Domain-facing Google provider

`app.google_calendar.GoogleCalendarProvider` implements the documented event
retrieval, listing, and creation signatures from
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
and any other status. Documented transport failures while executing the
request (`httplib2.HttpLib2Error`, Google authentication `TransportError`)
also become `ProviderFailureError`. Only the status and the machine-readable
reasons are interpreted; Google error messages never cross the provider
boundary, and the raw provider exception is not retained as the translated
error's cause. Translation failures for unsupported response shapes, such as
all-day events, still raise `KeyError` as documented below.

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

**REAL PROVIDER VERIFICATION NOT PERFORMED** for listing. Controlled SDK and HTTP
tests establish request construction, translation, and public behavior only.

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

- The input is a titled, timed event with `id`, `summary`, `start.dateTime`, and
  `end.dateTime`. Missing required fields raise `KeyError`; no placeholder title,
  identifier, or timestamp is invented.
- Timestamps are preserved as strings without parsing, timezone conversion, or
  additional format validation. Public model validation checks their string type.
- Google's all-day events use `start.date` and `end.date` instead of `dateTime`.
  They are unsupported by this mapper and raise `KeyError`; dates are not silently
  converted to midnight timestamps.
- Google's end boundary is exclusive. It is copied unchanged; this mapper does
  not adjust the duration or define new public interval semantics.
- Sparse cancelled event responses may lack required fields and are unsupported.
  This function does not define HTTP error handling.

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

`GoogleCalendarProvider.replace_event` makes one
`client.events().update(calendarId=..., eventId=..., body=...).execute()` call.
It sends `summary`, `start.dateTime`, and `end.dateTime`, then translates the
result into the four-field Event. It uses the shared Google HTTP/transport error
translation and performs no retries. Client ownership remains request-scoped.
Google's [events.update documentation](https://developers.google.com/workspace/calendar/api/v3/reference/events/update)
specifies full resource replacement, not patch semantics. Provider-only editable
fields omitted from the update are not preserved by this service; use a disposable,
non-recurring, titled timed event with no guests for verification.

**REAL PROVIDER VERIFICATION NOT PERFORMED** for PUT in this change.
Controlled SDK tests establish request construction and translation, not live
authorization or Google behavior. Before final release, Nicolas and a reviewer:

1. Complete local setup above using the read/write scope and a fresh token.
2. Create a disposable titled timed event in Google Calendar; obtain its event
   ID using the existing verification instructions above.
3. Start the service and run the PUT and GET example in
   [CONTRACT.md](CONTRACT.md#replace-event--nicolas-ollivier-51-operation-4).
4. Expect PUT 200 and all three replacement values in the returned Event, then
   GET 200 with the same complete values (allow Google's timestamp formatting).
   Verify the new title and interval in Google Calendar as well.
5. Record request, expected/observed values, date, reviewer, and cleanup in the
   owner-reviewed PR without secrets. Delete the disposable event in Google Calendar.

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

On October 6, 2026, [Airbus-A330](https://github.com/Airbus-A330/OSPSD-Team-2/pull/21#issuecomment-6028772243)
and [LeonLiu0204](https://github.com/Airbus-A330/OSPSD-Team-2/pull/21#issuecomment-6028796751)
reported successful end-to-end verification against the real provider.

On October 12, 2026, a separate live verification for #24 was run locally for
LeonLiu0204 using desktop OAuth with the read-only event scope. A test event was
created in the authenticated account's primary calendar through Google Calendar:
`OSPSD Provider Test`, 16:00–16:30 America/New_York, with no guests.

Using the real client from `build_google_calendar_client()`,
`GoogleCalendarProvider(client, calendar_id="primary").get_event(event_id)`
returned an `Event`. Assertions verified exactly these four fields against the
created event and confirmed that the provider timestamps were preserved:

```json
{
  "id": "28bd3p9jnnl2qojjmdpbb7ld1q",
  "title": "OSPSD Provider Test",
  "start": "2026-10-12T16:00:00-04:00",
  "end": "2026-10-12T16:30:00-04:00"
}
```

This verifies the concrete provider independently of HTTP wiring. The
credential-free HTTP integration test separately verifies application
substitution with a controlled provider. Credentials and tokens remain in
ignored local files and are not part of this evidence.

## Partial update verification

`GoogleCalendarProvider.patch_event` uses
[Google events.patch](https://developers.google.com/workspace/calendar/api/v3/reference/events/patch).
Only supplied fields are mapped: `title` to `summary`, `start` to `start.dateTime`,
and `end` to `end.dateTime`. Google preserves unspecified fields. Each PATCH uses
one SDK write; the application adds one GET when only one time boundary changes.
Google charges three quota units for PATCH. The existing `calendar.events` scope
and request-scoped client lifecycle are reused. Failures use the shared Google
classifier. No automatic retry or concurrency guarantee is added.

**REAL PROVIDER VERIFICATION NOT PERFORMED** for PATCH. Before final release:

1. Complete OAuth setup with write access and start the service.
2. Create a disposable event using the POST example above; keep its returned ID
   locally and record the original title/start/end.
3. Run the PATCH example in [CONTRACT.md](CONTRACT.md) with that ID. Expect 200;
   verify the title changed and both times stayed unchanged via GET and Google Calendar.
4. Patch only `end` to a later RFC3339 timestamp. Verify start/title remain unchanged.
5. Try `{}` and a start later than the stored end. Expect 400 and unchanged event
   values. Record expected/observed results without publishing private event data.
6. Delete the disposable event using the cleanup command above, then stop the server.

A failed write may have taken effect. Inspect current state after an ambiguous
failure before retrying or cleaning up; do not infer rollback from an error response.

# Calendar API: joint contract (Teams 2, 5, 7)

Oct 28, 2026 · Coordinated by @AD04 (Team 7)

## Status

This is version 4: version 3 rewritten in prose, with the reason for each rule, the open questions and their owners. Rule numbers match version 3 and the email thread.

Teams 2, 5, and 7 agreed to every rule on Oct 28.

## The problem

Teams 2, 5 and 7 each built an HTTP service that manages events in Google Calendar. HW2 asks the three teams to agree on one contract, so that a client written against one service works against the other two.

Before this contract, a client would have had to treat each server differently:

- Team 5 named the times start_time and end_time; Teams 2 and 7 used start and end.
- Team 2 answered every invalid request with 400. Teams 5 and 7 answered with 422, even when the body was not valid JSON.
- Error bodies differed: Team 2 sent code and message, Team 5 added retryable, and Team 7 added details.
- A permission failure was 403 permission_denied at Team 2 and 502 provider_auth_error at Team 7.
- Unknown fields in a body were rejected with 400 by Team 2, ignored by Team 5 and rejected with 422 by Team 7.
- A create that timed out returned 502 at Team 2, and 503 or 502 at Team 7. Team 5 had not built PUT yet.

Each difference would either break a client that moved between services or force it to guess. The rules below remove these differences for the operations all three teams share.

## Scope

The contract covers four operations. All three teams implement them on the same paths:

- Create: POST /events
- Get by id: GET /events/{event_id}
- Replace: PUT /events/{event_id}
- Delete: DELETE /events/{event_id}

The shared event has four fields: id, a string the provider assigns, plus title, start and end. Team 2 proposed this core on Oct 25; Team 5 agreed the same day and Team 7 on Oct 26.

Listing (GET /events), partial update (PATCH), all-day events, extra fields such as description and location, and calendar metadata are optional extensions. Each team may offer them and documents how they work.

Why this scope. All three teams already had create, get and delete, and two had PUT. Listing and PATCH exist at only some teams, with different parameters and meanings. Making them shared would have forced new work on some teams before the deadline, and a small contract every team keeps is worth more than a large one some teams break.

## The event and its operations

### Rule 1: PUT replaces the shared fields.

The body must contain title, start and end. Leaving one out, or sending it as null, is rejected with 422 invalid_input (rule 3). The id never changes, and each team decides and documents what PUT does to fields outside the shared four.

Why: "replace" should mean one thing. The teams answered differently on whether an omitted field is kept or cleared, so the contract requires all three shared fields and leaves nothing to guess. The id never changes because clients hold it as their handle on the event, and Team 2 asked that the contract define replacement only for the shared fields.

### Rule 8: success statuses.

Create returns 201, get 200, replace 200 and delete 204. A Location header on create is an optional extension that Team 7 offers.

Why: these are the standard HTTP meanings. 201 tells the client that a resource now exists, and 204 tells it there is no body to read.

### Rule 13: title.

POST and PUT require a string title that is non-empty after trimming leading and trailing whitespace. A missing, null or blank title is rejected with 422 invalid_input, and each team documents its maximum title length. When GET finds a provider event with a missing or empty title, it returns 200 with "title": "". A server never invents a title.

Why: a non-empty title is a requirement on writes, but events created outside our APIs, for example in the Google Calendar app, can have no title. Clients still need to read those. Trimming only decides whether a title is blank; no team has to store the trimmed title.

### Rule 15: the event in responses.

Create, get and replace return the event as a JSON object with at least id, title, start and end. Delete returns no body, and clients ignore fields they do not recognise.

Why: after a write, the client needs the stored state, including the id Google assigned and the times as stored. Ignoring unknown fields lets each team add extensions without breaking clients of the other two.

## Time

### Rule 2: timestamps.

Requests use RFC 3339 timestamp strings with an explicit UTC offset, Z or ±hh:mm. Numeric timestamps and timestamps without an offset are rejected with 422 invalid_input, and end must be an instant strictly after start. Responses represent the same instants as the stored provider timestamps, with any equivalent UTC offset; a server does not have to keep the offset the request used.

Why: a time without an offset is ambiguous, and a number could be seconds or milliseconds, so either can put an event at the wrong hour. The contract guarantees the instant, not how it is written. The teams already return different offsets, and making them match would cost work without helping a client that compares instants.

### Rule 14: time precision.

Times are whole seconds, and a server may drop sub-seconds from the times it receives; Team 7 does. A server that drops sub-seconds checks that end is after start after dropping them, so 10:00:00.1 to 10:00:00.9 is rejected there with 422 invalid_input. Clients that need the same result from every server send whole seconds.

Why: Google Calendar keeps event times to the second, so no server can promise more. Checking after the drop means a server never stores an event that ends when it starts. Team 7 proposed the last two sentences of this rule on Oct 28, Team 5 agreed the same day, and Team 2 subsequently adopted the shared rule in its tagged-contract integration.

## Bad requests and missing events

### Rule 3: invalid input.

A body that is not valid JSON gets 400 invalid_input. Valid JSON that breaks a rule gets 422 invalid_input: a missing, unknown or wrongly typed field, or a bad value such as a timestamp without an offset or an end not after start. A bad path or query parameter is also 422, and other invalid requests that are not validation failures get 400 invalid_input, for example Team 7 refusing to replace an all-day event.

Why: 400 says the server could not read the request, and 422 says it read the request and found a rule broken. A client can then tell a bug in its own serialisation from bad data a user entered. Team 5 proposed this split, and Team 2 agreed to move to it from 400 for everything.

### Rule 7: unknown fields.

A request body with a field the server does not know is rejected with 422 invalid_input, before the provider is called.

Why: a server that ignores unknown fields turns a typo into silent data loss. A client that sends descripton would get an event without its description and no error. Rejecting before the provider call means nothing is written.

### Rule 11: an event that does not exist.

GET, PUT and DELETE on an id the calendar does not have return 404 not_found.

### Rule 5: deleting an event that is already gone.

A DELETE repeated after it succeeded also returns 404 not_found.

Why, for both: a server cannot tell "deleted earlier" from "never existed" without keeping a history it does not have. One answer for both keeps every server simple, and a client that repeats a delete can treat 404 as "already gone".

## Errors and provider failures

### Rule 4: the error body.

Every error response is {"error": {"code": "...", "message": "...", "retryable": false}}. code, message and retryable are required; sanitised details are optional, and clients ignore keys they do not know. retryable, not the status, tells the client whether to retry, and a create or replace whose outcome is unknown has retryable: false even when a Retry-After header is present.

Why: one shape means a client writes one error handler for all three services. The status alone can mislead, because a 502 from a timed-out create must not be retried while many other server errors can. A duplicate event is worse than a wait, so retryable: false always wins.

### Rule 12: shared error codes.

The codes in rules 3 to 11 are shared: invalid_input, not_found, access_denied, provider_error and provider_unavailable. A team may use another code only for a case this contract does not cover, such as internal_error for a 500.

Why: clients branch on code, so the same failure must carry the same code at every server.

### Rule 9: provider failures.

- 403 access_denied when the configured provider identity lacks permission for the operation.
- 502 provider_error for an invalid or unexpected provider response, or a write whose outcome is unknown (rule 6).
- 503 provider_unavailable when the provider is temporarily unavailable, with Retry-After when there is a meaningful wait.

Why: the three cases call for different client behaviour. A permission problem needs someone to fix the configuration, so retrying is pointless; temporary unavailability is worth retrying later, and Retry-After says when. Team 7 had used 502 for a permission denial, because the service rather than the caller is denied, and accepted 403 because Teams 2 and 5 both preferred it.

### Rule 6: a create or replace whose outcome is unknown.

When a create or replace times out, the server returns 502 provider_error with retryable: false. It never retries the write on its own, and the client should know that sending it again may create a duplicate.

Why: Google may have written the event before the connection failed. POST is not idempotent at Teams 2 and 7, so a blind retry can create a second event, and only the client can decide whether to check and resend.

### Rule 10: coordination.

Arda Dinc (Team 7) coordinates this memo, as Teams 2 and 5 agreed.

## Where teams may still differ

The contract leaves these choices to each team, and each team documents its own:

- Fields outside the shared four on PUT (rule 1): Team 5 keeps them and Team 7 clears them. Team 2 clears fields outside the shared model because its Google Calendar events.update request contains only the shared editable fields (title, start, and end).
- Output offset (rule 2): Teams 2 keep the offset they were given; Team 5 uses the provider-returned timestamps and does not guarantee preservation of the original request offset; Team 7 returns UTC with Z.
- Sub-seconds (rule 14): Team 7 drops them. Team 5 does not deliberately truncate fractional seconds in its application code; returned precision follows the provider-returned timestamps. Team 2 does not deliberately truncate fractional seconds in application code; returned precision follows the provider-returned timestamp.
- Maximum title length (rule 13): Team 7 allows 1024 characters. Team 5 currently sets no explicit application-level maximum title length. Provider limits still apply. Team 2 currently sets no explicit application-level maximum title length; provider limits still apply.
- Stored title (rule 13): Team 7 stores the title without its leading and trailing whitespace. Team 5 also trims leading and trailing whitespace before sending titles to Google. Team 2 uses trimming only to determine whether a title is blank; it does not deliberately trim the title before sending it to Google.
- Location header on create (rule 8): Team 7 sends one.
- Extensions: Team 2 offers listing and PATCH. Team 5 offers PATCH, which updates every field, and metadata for the primary calendar. Team 7 offers listing with a time window and cursor paging, plus description, location, a read-only all_day and web_link.

## What each team changes, and who owns it

Each team owns the changes to its own service. [To fill: when they are due, once the handout or the next checkpoint sets a date.]

Team 2 returns 422 instead of 400 for valid JSON that breaks a rule, including unknown fields (rules 3 and 7). It adds retryable to every error body (rule 4) and returns 503 provider_unavailable, not 502, when the provider is temporarily unavailable (rule 9). It renames permission_denied to access_denied (rule 12).

Team 5 renames start_time and end_time to start and end, and builds PUT (rule 1). It returns 400 instead of 422 for a body that is not valid JSON (rule 3), and rejects unknown fields with 422 instead of ignoring them (rule 7). Team 5 currently returns 201 for POST, 200 for GET and PATCH, and 204 with an empty body for DELETE. POST does not set a Location header, which is optional under rule 8. These existing success statuses need no change. PUT is not implemented yet and will return 200 when added.

Team 7 returns 400 instead of 422 for a body that is not valid JSON (rule 3), and adds retryable to every error body (rule 4). It returns 502 with retryable: false, not 503, when a create or replace times out (rule 6), and 403 instead of 502 when the provider denies access (rule 9). It renames validation_error and invalid_request to invalid_input, event_not_found to not_found, and provider_auth_error to access_denied (rule 12). Team 7 tracks each change as an issue, #31 to #35; the renaming is in review.

## Provider constraints

All three services use Google Calendar, but each reaches it differently, and that limits what it can do:

- Which calendar. Team 2 uses the calendar set in GOOGLE_CALENDAR_ID, defaulting to the authenticated account's primary calendar. Team 5 uses the authenticated account's primary calendar. Team 7 uses one calendar set in its configuration, reached through a Google service account.
- Which events can be written. All three write timed events only. Team 2 writes titled events whose start and end carry a UTC offset. Team 7 can read existing all-day and recurring events, but PUT on them returns 400.
- Event ids. Google assigns them at all three teams. Team 2 treats them as opaque non-empty strings, and Team 7 as opaque strings of 1 to 1024 characters.
- Attendees. Team 2's public event model has none. Team 7 cannot support them, because a service account cannot invite people without domain-wide delegation. Team 5 does not expose attendees in its public request model.

- Repeating a create. At Teams 2 and 7 it creates a second event: POST is not idempotent, and uncertain writes are not retried automatically. At Team 5, repeating a successful POST creates another event. POST is not idempotent, and uncertain creation results are not automatically retried.

Team 5 notes that its limits describe its current implementation, not everything Google Calendar can do.

## Unresolved questions and owners

1. Team 5's PUT is not built yet. Rule 1 is a commitment for Team 5, not what it does today. Owner: Team 5.
2. A timed-out create cannot be checked with the shared core alone. Rule 6 tells the client not to resend blindly, but the failed create returned no id and listing is not shared. At Team 5, which has no listing, a client cannot find out whether the event exists. A shared listing or an idempotency key on create would close this. Owner: [proposed: Arda (Team 7) raises it at the next checkpoint].
3. Listing and PATCH are not shared. Teams 2 and 7 list with different parameters, Team 5 does not list, and Teams 2 and 5 mean different things by PATCH. Whether to standardise either is open. Owner: [to assign].
4. Fields outside the shared four behave differently on PUT. A client that sets description or location gets different results at each service. We accept this for now and revisit it if a client needs those fields. Owner: [to assign].
5. [To fill if the handout requires it: the shared Python contract package and conformance checks, with an owner per team.]

## How we reached this

- Oct 25: Alexander Freedman (Team 2) proposed the shared core, and Juno Lee (Team 5) replied the same day.
- Oct 26: Arda Dinc (Team 7) replied and wrote version 1 of this memo.
- Oct 27: Team 2 sent its answers (version 2) and a follow-up on the open questions. Jim Lo (Team 5) sent Team 5's answers and its status mapping on Slack. Version 3 merged them, and Team 7 accepted Team 5's mapping, including 403.
- Oct 27, evening: Team 2 agreed to version 3. Jim filled in Team 5's four open cells and asked about rules 2, 13 and 14.
- Oct 28: Juno proposed new wording for rules 2, 13 and 14. Team 2 agreed and clarified that trimming only decides whether a title is blank. Team 7 agreed and proposed the sub-second sentence in rule 14.
- Oct 28: Juno confirmed by email and on Slack that Team 5 agrees to every rule.

- Oct 28: Alexander confirmed by email that Team 2 agrees to every rule.

The discussion is on the email thread "HW2 Calendar Shared API Coordination (OSPSD)" and in the #calendar channel on NYU Slack.

Email Thread: https://drive.google.com/file/d/1qE08aNXGlD3jSa44s1nrngVPM_KyZNqR/view?usp=drive_link

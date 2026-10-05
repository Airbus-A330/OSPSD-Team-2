# Provider Integration

This document records facts and assumptions about the selected external provider.

Do not copy provider-specific behavior into `CONTRACT.md` unless it becomes part of our own public contract.

## Selected Provider

Google Calendar API v3, accessed through Google's Python client libraries.

## Official Documentation

- [Google Calendar Python quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python)
- [Google Calendar API scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Google OAuth security best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices)

## Authentication

Local development uses Google's OAuth 2.0 installed-application flow. The service
requests this read-only scope:

```text
https://www.googleapis.com/auth/calendar.events.readonly
```

This scope permits reading events but does not permit changes. It is the narrowest
scope needed for the planned event retrieval operation.

### Local setup

1. Create or select a Google Cloud project and enable the Google Calendar API.
2. Configure the Google Auth consent screen. If the app is in testing mode, add
   each teammate's Google account as a test user.
3. Create an OAuth client with the **Desktop app** application type.
4. Download the client configuration and save it outside version control. By
   default, the code reads `credentials.json` from the repository root.
5. Install dependencies with `pip install -r requirements.txt`.
6. Run the manual verification command below. On first use, a browser opens for
   consent and the resulting authorization is stored in `token.json`.

Alternative locations can be supplied with these environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_CALENDAR_CREDENTIALS_FILE` | `credentials.json` | Downloaded desktop OAuth client configuration |
| `GOOGLE_CALENDAR_TOKEN_FILE` | `token.json` | Generated user access and refresh token data |

Both default files, `.env` files, and downloaded `client_secret*.json` files are
ignored by Git. Never commit or share these files. Store them securely and revoke
the authorization in the Google account when it is no longer needed.

If the requested scopes change, delete the local token file and authorize again.

### Manual authentication verification

From the repository root, run:

```bash
python -c "from app.google_calendar import build_google_calendar_client; client = build_google_calendar_client(); client.events().list(calendarId='primary', maxResults=1).execute(); print('Authentication successful')"
```

The first run should open Google's consent flow. A successful request prints the
confirmation message and creates the configured token file. This command
contacts the real provider and is intentionally excluded from automated tests and
CI.

## Provider Operations

| Service behavior | Provider API/SDK operation | Notes |
|---|---|---|
| Construct an authenticated client | `googleapiclient.discovery.build("calendar", "v3", ...)` | No calendar operation is implemented in this issue |

## Field Mapping

| Provider field | Domain field | Notes |
|---|---|---|
| TBD | TBD | |

## Provider Limitations

- The installed-application OAuth flow requires an interactive browser on first
  authorization.
- The configured scope is read-only and cannot create, update, or delete events.
- Local token storage is suitable for development only; a production deployment
  would require an appropriate secure credential store and authentication design.

## Verified Assumptions

- Google's official Python quickstart uses desktop OAuth credentials, caches user
  authorization in a local token file, refreshes expired credentials when a
  refresh token is available, and constructs Calendar API v3 with
  `googleapiclient.discovery.build`.
- Unit tests verify the same client-construction branches without real credentials
  or network access.

## Unverified Assumptions

- A teammate must complete the documented manual verification with the team's
  Google Cloud project and test calendar; no real credentials are available in CI.

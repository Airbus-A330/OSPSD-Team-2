"""Google Calendar SDK operations; results require translation before HTTP use."""

from typing import Any


def get_event(client: Any, *, calendar_id: str, event_id: str) -> dict[str, object]:
    """Read one event using an already configured Google Calendar v3 client.

    Args:
        client: Authenticated client owned and configured by the caller. Uses
            Any because the SDK generates service methods dynamically.
        calendar_id: Google calendar identifier, or ``primary`` for the
            authenticated user's primary calendar. No default is selected here.
        event_id: Google event ID within that calendar, not an iCalendar UID.

    Returns:
        Raw Google event data for the translation boundary, not an HTTP response.

    Raises:
        googleapiclient.errors.HttpError: If Google rejects the request.
            Transport failures also propagate to the caller.
    """
    return client.events().get(calendarId=calendar_id, eventId=event_id).execute()

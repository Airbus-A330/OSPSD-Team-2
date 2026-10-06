"""Translate Google Calendar response data into public domain models."""

from collections.abc import Mapping
from typing import Any

from app.models import Event


def translate_google_event(provider_event: Mapping[str, Any]) -> Event:
    """Translate a titled, timed Google event without exposing its metadata.

    Args:
        provider_event: JSON response from the Google Calendar events API.

    Returns:
        The event's identifier, title, and unchanged dateTime strings.
    """
    return Event(
        id=provider_event["id"],
        title=provider_event["summary"],
        start=provider_event["start"]["dateTime"],
        end=provider_event["end"]["dateTime"],
    )

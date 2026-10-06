"""Credential-free tests of Google event translation."""

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from app.google_calendar import translate_google_event
from app.models import Event


@pytest.fixture
def provider_event() -> dict[str, Any]:
    return {
        "id": "event123",
        "summary": "Team meeting",
        "start": {
            "dateTime": "2026-10-07T09:00:00-04:00",
            "timeZone": "America/New_York",
        },
        "end": {
            "dateTime": "2026-10-07T10:00:00-04:00",
            "timeZone": "America/New_York",
        },
        "kind": "calendar#event",
        "etag": '"123456"',
        "iCalUID": "event123@google.com",
        "organizer": {"email": "organizer@example.com"},
    }


def test_translates_required_fields(provider_event: dict[str, Any]) -> None:
    assert translate_google_event(provider_event) == Event(
        id="event123",
        title="Team meeting",
        start="2026-10-07T09:00:00-04:00",
        end="2026-10-07T10:00:00-04:00",
    )


def test_serialization_exposes_only_public_fields(
    provider_event: dict[str, Any],
) -> None:
    assert translate_google_event(provider_event).model_dump() == {
        "id": "event123",
        "title": "Team meeting",
        "start": "2026-10-07T09:00:00-04:00",
        "end": "2026-10-07T10:00:00-04:00",
    }


def test_translation_does_not_modify_provider_data(
    provider_event: dict[str, Any],
) -> None:
    original = deepcopy(provider_event)
    translate_google_event(provider_event)
    assert provider_event == original


def test_metadata_is_not_required(provider_event: dict[str, Any]) -> None:
    required_fields = {key: provider_event[key] for key in ("id", "summary")}
    for key in ("start", "end"):
        required_fields[key] = {"dateTime": provider_event[key]["dateTime"]}
    assert translate_google_event(required_fields) == translate_google_event(
        provider_event
    )


@pytest.mark.parametrize("field", ["id", "summary", "start", "end"])
def test_missing_required_field_is_not_fabricated(
    provider_event: dict[str, Any], field: str
) -> None:
    del provider_event[field]
    with pytest.raises(KeyError, match=field):
        translate_google_event(provider_event)


@pytest.mark.parametrize("field", ["start", "end"])
def test_date_only_time_is_not_converted_to_a_timestamp(
    provider_event: dict[str, Any], field: str
) -> None:
    provider_event[field] = {"date": "2026-10-07"}
    with pytest.raises(KeyError, match="dateTime"):
        translate_google_event(provider_event)


@pytest.mark.parametrize("field", ["id", "summary", "start", "end"])
@pytest.mark.parametrize("value", [None, 123])
def test_mapped_values_must_be_strings(
    provider_event: dict[str, Any], field: str, value: int | None
) -> None:
    if field in ("start", "end"):
        provider_event[field]["dateTime"] = value
    else:
        provider_event[field] = value
    with pytest.raises(ValidationError):
        translate_google_event(provider_event)

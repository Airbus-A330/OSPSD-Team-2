"""Tests for the provider-independent public Event contract."""

import json

import pytest
from pydantic import ValidationError

from app.models import Event


@pytest.fixture
def event_data() -> dict[str, str]:
    return {
        "id": "event-123",
        "title": "Team Meeting",
        "start": "2026-10-01T10:00:00-04:00",
        "end": "2026-10-01T11:00:00-04:00",
    }


def test_constructs_event_from_public_fields(event_data: dict[str, str]) -> None:
    event = Event(**event_data)

    assert event.id == event_data["id"]
    assert event.title == event_data["title"]
    assert event.start == event_data["start"]
    assert event.end == event_data["end"]


def test_serializes_only_public_fields(event_data: dict[str, str]) -> None:
    event = Event(**event_data)

    assert event.model_dump() == event_data
    assert json.loads(event.model_dump_json()) == event_data


@pytest.mark.parametrize("field", ["id", "title", "start", "end"])
def test_requires_each_public_field(event_data: dict[str, str], field: str) -> None:
    del event_data[field]

    with pytest.raises(ValidationError) as exc_info:
        Event.model_validate(event_data)

    assert [(error["loc"], error["type"]) for error in exc_info.value.errors()] == [
        ((field,), "missing")
    ]


@pytest.mark.parametrize("field", ["id", "title", "start", "end"])
@pytest.mark.parametrize("value", [None, 123, True, [], {}])
def test_rejects_non_string_fields(
    event_data: dict[str, str], field: str, value: object
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Event.model_validate({**event_data, field: value})

    assert [(error["loc"], error["type"]) for error in exc_info.value.errors()] == [
        ((field,), "string_type")
    ]


@pytest.mark.parametrize(
    "timestamp", ["2026-10-01T14:00:00Z", "2026-10-01T19:30:00.123+05:30"]
)
@pytest.mark.parametrize("field", ["start", "end"])
def test_preserves_timestamp_strings(
    event_data: dict[str, str], field: str, timestamp: str
) -> None:
    event_data[field] = timestamp

    event = Event(**event_data)

    assert json.loads(event.model_dump_json()) == event_data

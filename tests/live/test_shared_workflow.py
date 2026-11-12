"""Opt-in real HTTP-to-Google workflow; never run with normal CI credentials."""

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app import composition
from app.event_cache import EventCache
from app.main import create_app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_CALENDAR") != "1",
    reason="Opt-in live Google verification requires designated test credentials",
)


def require(condition: bool, message: str) -> None:
    """Report only sanitized verification failures, never response payloads."""
    if not condition:
        pytest.fail(message, pytrace=False)


def check_event(response: Response, status: int, fields: dict[str, str]) -> str:
    require(response.status_code == status, "Unexpected event response status")
    try:
        data = response.json()
        valid = (
            set(data) == {"id", "title", "start", "end"}
            and isinstance(data["id"], str)
            and bool(data["id"])
            and data["title"] == fields["title"]
            and all(
                datetime.fromisoformat(data[key]) == datetime.fromisoformat(fields[key])
                for key in ("start", "end")
            )
        )
    except (ValueError, TypeError, KeyError):
        pytest.fail("Invalid event response shape", pytrace=False)
    require(valid, "Stored event does not match the shared request")
    return str(data["id"])


def check_not_found(response: Response) -> None:
    require(response.status_code == 404, "Expected a missing-event response")
    require(
        response.json()
        == {
            "error": {
                "code": "not_found",
                "message": "Event not found",
                "retryable": False,
            }
        },
        "Unexpected missing-event error envelope",
    )


def test_live_shared_create_read_replace_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create only disposable data, force real reads, and always attempt cleanup."""
    require(
        bool(os.getenv("GOOGLE_CALENDAR_ID")),
        "Set a designated test GOOGLE_CALENDAR_ID",
    )
    token = Path(os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", "token.json"))
    require(token.is_file(), "Authorize locally first; saved OAuth token is missing")
    monkeypatch.setattr(composition, "event_cache", EventCache(ttl_seconds=0))
    fields = {
        "title": "OSPSD disposable contract verification " + uuid4().hex,
        "start": "2030-01-07T15:00:00Z",
        "end": "2030-01-07T15:30:00Z",
    }
    replacement = {
        **fields,
        "title": fields["title"] + " replaced",
        "end": "2030-01-07T17:00:00+01:00",
    }
    event_id: str | None = None
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        try:
            response = client.post("/events", json=fields)
            # Capture a returned ID before checking other fields so cleanup also
            # runs when a successful provider write has a bad public response.
            if response.status_code == 201:
                candidate = response.json().get("id")
                if isinstance(candidate, str) and candidate:
                    event_id = candidate
            event_id = check_event(response, 201, fields)
            path = "/events/" + event_id
            require(
                check_event(client.get(path), 200, fields) == event_id,
                "GET changed the event ID",
            )
            require(
                check_event(client.put(path, json=replacement), 200, replacement)
                == event_id,
                "PUT changed the event ID",
            )
            check_event(client.get(path), 200, replacement)
            deleted = client.delete(path)
            require(
                deleted.status_code == 204 and deleted.content == b"",
                "DELETE did not return empty 204",
            )
            check_not_found(client.delete(path))
            check_not_found(client.get(path))
            check_not_found(client.put(path, json=replacement))
        finally:
            if event_id is not None:
                cleanup = client.delete("/events/" + event_id)
                require(
                    cleanup.status_code in (204, 404),
                    "Cleanup failed; calendar owner must remove the disposable verification event",
                )

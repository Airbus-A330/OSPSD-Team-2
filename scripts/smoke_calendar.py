"""Exercise the deployed shared Calendar HTTP contract without logging contents."""

import time
from datetime import datetime
from urllib.parse import quote
from uuid import uuid4

import httpx
from calendar_contract import Event


def require(condition: bool, message: str) -> None:
    """Fail with a fixed message safe to retain in delivery evidence."""
    if not condition:
        raise RuntimeError(message)


def check_event(response: httpx.Response, status: int, fields: dict[str, str]) -> str:
    """Check the shared representation and equivalent stored instants."""
    require(response.status_code == status, "Unexpected event status")
    payload = response.json()
    require(set(payload) == {"id", "title", "start", "end"}, "Invalid event shape")
    event = Event.model_validate(payload)
    require(bool(event.id) and event.title == fields["title"], "Event values differ")
    for key in ("start", "end"):
        require(
            datetime.fromisoformat(getattr(event, key))
            == datetime.fromisoformat(fields[key]),
            "Stored instants differ",
        )
    return event.id


def check_missing(response: httpx.Response) -> None:
    """Verify the shared missing-resource envelope without retaining its body."""
    require(response.status_code == 404, "Expected missing event")
    error = response.json()["error"]
    require(
        error["code"] == "not_found" and error["retryable"] is False,
        "Invalid missing-event error",
    )


def smoke_calendar(client: httpx.Client, report: dict[str, object]) -> None:
    """Run CRUD once and attempt cleanup even after a partial failure.

    Args:
        client: Authenticated client for the dedicated deployed test calendar.
        report: Sanitized delivery evidence, updated even on failure.

    Raises:
        RuntimeError: If readiness, contract behavior, or cleanup fails.
        httpx.HTTPError: If transport fails; writes are never retried.
    """
    deadline = time.monotonic() + 300
    while True:
        try:
            if client.get("/readyz").status_code == 200:
                break
        except httpx.TransportError:
            pass  # Only safe readiness probes retry Render's bounded cold start.
        require(time.monotonic() < deadline, "Readiness timed out")
        time.sleep(5)

    fields = {
        "title": "OSPSD delivery smoke " + uuid4().hex,
        "start": "2030-01-07T15:00:00Z",
        "end": "2030-01-07T15:30:00Z",
    }
    replacement = {**fields, "title": fields["title"] + " replaced"}
    event_id: str | None = None
    report["cleanup"] = "unknown_create_outcome"
    try:
        response = client.post("/events", json=fields)
        # Capture IDs before validation so a malformed successful response can
        # still be cleaned up. Never retry POST after an uncertain response.
        payload = response.json()
        if isinstance(payload, dict):
            candidate = payload.get("id")
            if isinstance(candidate, str) and candidate:
                event_id = candidate
        checked_id = check_event(response, 201, fields)
        require(checked_id == event_id, "Invalid create ID")
        event_id = checked_id
        path = "/events/" + quote(event_id, safe="")
        require(
            check_event(client.get(path), 200, fields) == event_id, "GET changed ID"
        )
        require(
            check_event(client.put(path, json=replacement), 200, replacement)
            == event_id,
            "PUT changed ID",
        )
        require(
            check_event(client.get(path), 200, replacement) == event_id,
            "Replacement read-back changed ID",
        )
        deleted = client.delete(path)
        require(deleted.status_code == 204 and not deleted.content, "Invalid DELETE")
        check_missing(client.get(path))
        check_missing(client.delete(path))
        report["smoke"] = "passed"
    finally:
        if event_id is not None:
            report["cleanup"] = "failed"
            path = "/events/" + quote(event_id, safe="")
            require(client.delete(path).status_code in (204, 404), "Cleanup failed")
            check_missing(client.get(path))
            report["cleanup"] = "confirmed"

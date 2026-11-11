import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000/events"


def check(method, path="", body=None, status=200, error=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urlopen(req, timeout=30)
    except HTTPError as exc:
        response = exc
    with response:
        actual = response.code
        raw = response.read()

    assert actual == status, f"{method} {path}: expected {status}, got {actual}"
    value = json.loads(raw) if raw else None
    if error:
        code, message = error
        assert value == {"error": {"code": code, "message": message}}, value
    if status == 204:
        assert raw == b"", "DELETE must return an empty body"
    print(f"PASS {method} {path}: {actual}")
    return value


def event_matches(event, expected):
    assert set(event) == {"id", "title", "start", "end"}, event
    assert all(isinstance(v, str) for v in event.values()), event
    assert event["title"] == expected["title"], event
    for field in ("start", "end"):
        # Compare instants: Google may return equivalent timezone formatting.
        assert datetime.fromisoformat(event[field].replace("Z", "+00:00")) == \
            datetime.fromisoformat(expected[field].replace("Z", "+00:00"))


start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
    minute=0, second=0, microsecond=0
)
original = {
    "title": "OSPSD release verification",
    "start": start.isoformat(),
    "end": (start + timedelta(hours=1)).isoformat(),
}
event_id = None
deleted = False

try:
    # Create, retrieve, and repeat GET to exercise the cache.
    created = check("POST", body=original, status=201)
    event_id = created["id"]
    path = "/" + event_id
    event_matches(created, original)
    for _ in range(2):
        fetched = check("GET", path)
        assert fetched["id"] == event_id
        event_matches(fetched, original)

    # Listing is bounded; it need not include our newly created event.
    listed = check("GET", "?limit=2")
    assert isinstance(listed, list) and len(listed) <= 2
    for event in listed:
        assert set(event) == {"id", "title", "start", "end"}

    # Invalid limits and blank identifiers.
    for limit in ("0", "-1", "101", "abc"):
        check("GET", "?limit=" + limit, status=400,
              error=("invalid_input", "Invalid event limit"))
    check("GET", "/%20", status=400,
          error=("invalid_input", "Invalid event ID"))

    # Invalid create bodies.
    for bad in (
        {},
        {**original, "title": " "},
        {**original, "title": None},
        {**original, "extra": True},
        {**original, "start": "2026-10-22"},
        {**original, "end": original["start"]},
    ):
        check("POST", body=bad, status=400,
              error=("invalid_input", "Invalid event data"))

    # PUT requires a full replacement.
    check("PUT", path, {"title": "Incomplete"}, status=400,
          error=("invalid_input", "Invalid event replacement"))
    replacement = {
        "title": "OSPSD replaced",
        "start": (start + timedelta(hours=2)).isoformat(),
        "end": (start + timedelta(hours=3)).isoformat(),
    }
    event_matches(check("PUT", path, replacement), replacement)
    event_matches(check("GET", path), replacement)

    # PATCH rejects empty, null, unknown, and invalid interval values.
    for bad in (
        {}, {"title": None}, {"extra": True},
        {"start": (start + timedelta(hours=4)).isoformat()},
    ):
        check("PATCH", path, bad, status=400,
              error=("invalid_input", "Invalid input"))
    event_matches(check("GET", path), replacement)

    # Title-only PATCH preserves times and updates cached GET immediately.
    patched = {**replacement, "title": "OSPSD patched"}
    event_matches(check("PATCH", path, {"title": patched["title"]}), patched)
    event_matches(check("GET", path), patched)

    # Delete must invalidate cached data.
    check("DELETE", path, status=204)
    deleted = True
    for method in ("GET", "DELETE", "PUT", "PATCH"):
        body = replacement if method == "PUT" else (
            {"title": "Missing"} if method == "PATCH" else None
        )
        check(method, path, body, status=404,
              error=("not_found", "Event not found"))

    print("\nALL CHECKS PASSED")

finally:
    if event_id and not deleted:
        print("Cleaning up disposable event:", event_id)
        check("DELETE", "/" + event_id, status=204)
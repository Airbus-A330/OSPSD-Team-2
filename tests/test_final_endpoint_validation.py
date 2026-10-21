"""Final endpoint input audit: invalid requests stop before Google setup."""

import json
from itertools import combinations
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.models import Event
from app.providers import EventProvider

BODY = {
    "title": " Meeting 会議 ",
    "start": "2026-10-22T10:00:00Z",
    "end": "2026-10-22T11:00:00Z",
}
INVALID_VALUES: list[object] = [
    None,
    [],
    "private-body",
    42,
    True,
    {},
    {**BODY, "extra": "private-body"},
    {**BODY, "title": ""},
    {**BODY, "title": "   "},
    {**BODY, "title": 42},
    {**BODY, "start": None},
    {**BODY, "start": "invalid"},
    {**BODY, "start": "2026-10-22T10:00:00"},
    {**BODY, "start": "2026-02-30T10:00:00Z"},
    {**BODY, "start": "2026-10-22T25:00:00Z"},
    {**BODY, "start": "2026-10-22T10:00:00+24:00"},
    {**BODY, "end": BODY["start"]},
    {**BODY, "end": "2026-10-22T09:00:00Z"},
]


@pytest.fixture
def setup_spy(monkeypatch: pytest.MonkeyPatch) -> Mock:
    setup = Mock(side_effect=AssertionError("Invalid input must not start OAuth"))
    monkeypatch.setattr(main, "build_google_calendar_client", setup)
    return setup


def assert_invalid(
    method: str,
    path: str,
    content: bytes,
    setup: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.request(
            method, path, content=content, headers={"content-type": "application/json"}
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"
    assert set(response.json()["error"]) == {"code", "message"}
    setup.assert_not_called()
    assert "private-body" not in response.text + caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize(
    "method,path",
    [("POST", "/events"), ("PUT", "/events/opaque-id"), ("PATCH", "/events/opaque-id")],
)
@pytest.mark.parametrize("value", INVALID_VALUES)
def test_invalid_body_shapes_and_values(
    method: str,
    path: str,
    value: object,
    setup_spy: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert_invalid(method, path, json.dumps(value).encode(), setup_spy, caplog)


@pytest.mark.parametrize(
    "method,path", [("POST", "/events"), ("PUT", "/events/opaque-id")]
)
@pytest.mark.parametrize("missing", ["title", "start", "end"])
def test_full_write_requires_every_editable_field(
    method: str,
    path: str,
    missing: str,
    setup_spy: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert_invalid(
        method,
        path,
        json.dumps({k: v for k, v in BODY.items() if k != missing}).encode(),
        setup_spy,
        caplog,
    )


@pytest.mark.parametrize("field", ["title", "start", "end"])
def test_patch_explicit_null_is_invalid(
    field: str, setup_spy: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    assert_invalid(
        "PATCH",
        "/events/opaque-id",
        json.dumps({field: None}).encode(),
        setup_spy,
        caplog,
    )


@pytest.mark.parametrize(
    "method,path",
    [("POST", "/events"), ("PUT", "/events/opaque-id"), ("PATCH", "/events/opaque-id")],
)
@pytest.mark.parametrize(
    "content", [b"", b'{"private-body":', b'{"title":"private-body\xff"}']
)
def test_empty_malformed_json_and_invalid_utf8(
    method: str,
    path: str,
    content: bytes,
    setup_spy: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert_invalid(method, path, content, setup_spy, caplog)


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("encoded", ["%20", "%09%20"])
def test_whitespace_ids_stop_before_provider(
    method: str, encoded: str, setup_spy: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    assert_invalid(
        method, "/events/" + encoded, json.dumps(BODY).encode(), setup_spy, caplog
    )


@pytest.mark.parametrize("limit", ["0", "101", "-1", "abc", "1.5", "1.0", ""])
def test_invalid_list_limit_stops_before_provider(
    limit: str, setup_spy: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    assert_invalid("GET", "/events?limit=" + limit, b"", setup_spy, caplog)


@pytest.fixture
def provider() -> Iterator[Mock]:
    controlled = Mock(spec=EventProvider)
    current = Event(id=" opaque-会議 ", **BODY)
    controlled.get_event.return_value = current
    controlled.create_event.side_effect = lambda event: Event(
        id=current.id, **event.model_dump()
    )
    controlled.replace_event.side_effect = lambda event_id, replacement: Event(
        id=event_id, **replacement.model_dump()
    )
    controlled.patch_event.side_effect = lambda event_id, changes: current.model_copy(
        update=changes.model_dump(exclude_unset=True)
    )
    controlled.list_events.return_value = []
    main.app.dependency_overrides[main.get_event_provider] = lambda: controlled
    try:
        yield controlled
    finally:
        main.app.dependency_overrides.pop(main.get_event_provider)


@pytest.mark.parametrize("offset", ["Z", "+05:30", "-04:00"])
@pytest.mark.parametrize(
    "method,path", [("POST", "/events"), ("PUT", "/events/%20opaque-会議%20")]
)
def test_valid_unicode_title_and_offsets_preserved(
    offset: str, method: str, path: str, provider: Mock
) -> None:
    body = {
        **BODY,
        "start": "2026-10-22T10:00:00" + offset,
        "end": "2026-10-22T11:00:00" + offset,
    }
    with TestClient(main.app) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == (201 if method == "POST" else 200)
    assert response.json() == {"id": " opaque-会議 ", **body}


@pytest.mark.parametrize(
    "fields", [fields for n in (1, 2, 3) for fields in combinations(BODY, n)]
)
def test_each_valid_patch_subset_preserves_omitted_fields(
    fields: tuple[str, ...], provider: Mock
) -> None:
    body = {key: BODY[key] for key in fields}
    with TestClient(main.app) as client:
        response = client.patch("/events/%20opaque-会議%20", json=body)
    assert response.status_code == 200
    assert response.json() == {"id": " opaque-会議 ", **BODY}
    event_id, changes = provider.patch_event.call_args.args
    assert event_id == " opaque-会議 "
    assert changes.model_dump(exclude_unset=True) == body


@pytest.mark.parametrize(
    "query,limit", [("", 10), ("?limit=1", 1), ("?limit=100", 100)]
)
def test_valid_list_limits(query: str, limit: int, provider: Mock) -> None:
    with TestClient(main.app) as client:
        assert client.get("/events" + query).status_code == 200
    provider.list_events.assert_called_once_with(limit)


@pytest.mark.parametrize(
    "method,provider_method", [("GET", "get_event"), ("DELETE", "delete_event")]
)
def test_opaque_identifiers_pass_unchanged(
    method: str, provider_method: str, provider: Mock
) -> None:
    with TestClient(main.app) as client:
        response = client.request(method, "/events/%20opaque-会議%20")
    assert response.status_code == (200 if method == "GET" else 204)
    getattr(provider, provider_method).assert_called_once_with(" opaque-会議 ")

"""Prove delivery failure gates and disposable smoke cleanup without credentials."""

import json
from pathlib import Path

import httpx
import pytest

from scripts.deploy_render import deploy_image, main
from scripts.smoke_calendar import smoke_calendar

IMAGE = "ghcr.io/airbus-a330/ospsd-team-2@sha256:" + "a" * 64


def calendar_transport(calls: list[str], *, failure: str = "") -> httpx.MockTransport:
    """Model an external Calendar API and bounded failures at the HTTP boundary."""
    stored: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        operation = request.method + " " + request.url.path
        calls.append(operation)
        if request.url.path == "/readyz":
            return httpx.Response(200)
        if request.method == "POST":
            stored.update(json.loads(request.content))
            stored["id"] = "owned-event"
            if failure == "lost_create":
                raise httpx.ReadTimeout("synthetic lost write response")
            payload = {**stored, "title": None} if failure == "bad_create" else stored
            return httpx.Response(201, json=payload)
        if request.method == "PUT":
            if failure == "replace":
                return httpx.Response(503)
            stored.update(json.loads(request.content))
        if request.method == "DELETE":
            if failure == "cleanup":
                return httpx.Response(503)
            if stored:
                stored.clear()
                return httpx.Response(204)
        if not stored:
            return httpx.Response(
                404, json={"error": {"code": "not_found", "retryable": False}}
            )
        return httpx.Response(200, json=stored)

    return httpx.MockTransport(handle)


def test_smoke_checks_full_shared_workflow_and_confirms_cleanup() -> None:
    calls: list[str] = []
    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://calendar.example", transport=calendar_transport(calls)
    ) as client:
        smoke_calendar(client, report)
    assert report == {"smoke": "passed", "cleanup": "confirmed"}
    assert calls == [
        "GET /readyz",
        "POST /events",
        "GET /events/owned-event",
        "PUT /events/owned-event",
        "GET /events/owned-event",
        "DELETE /events/owned-event",
        "GET /events/owned-event",
        "DELETE /events/owned-event",
        "DELETE /events/owned-event",
        "GET /events/owned-event",
    ]


@pytest.mark.parametrize("failure", ["bad_create", "replace"])
def test_smoke_cleans_up_returned_id_after_contract_failure(failure: str) -> None:
    calls: list[str] = []
    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://calendar.example",
        transport=calendar_transport(calls, failure=failure),
    ) as client:
        with pytest.raises((ValueError, RuntimeError)):
            smoke_calendar(client, report)
    assert report == {"cleanup": "confirmed"}
    assert calls[-2:] == ["DELETE /events/owned-event", "GET /events/owned-event"]
    assert calls.count("POST /events") == 1


def test_smoke_never_retries_an_uncertain_create() -> None:
    calls: list[str] = []
    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://calendar.example",
        transport=calendar_transport(calls, failure="lost_create"),
    ) as client:
        with pytest.raises(httpx.ReadTimeout):
            smoke_calendar(client, report)
    assert report == {"cleanup": "unknown_create_outcome"}
    assert calls == ["GET /readyz", "POST /events"]


def test_smoke_cleanup_failure_blocks_success() -> None:
    calls: list[str] = []
    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://calendar.example",
        transport=calendar_transport(calls, failure="cleanup"),
    ) as client:
        with pytest.raises(RuntimeError, match="Cleanup failed"):
            smoke_calendar(client, report)
    assert report == {"cleanup": "failed"}


@pytest.mark.parametrize("status", ["live", "update_failed", "canceled", "deactivated"])
def test_render_waits_for_the_requested_digest_deployment(status: str) -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"id": "dep-controlled"})
        return httpx.Response(200, json={"status": status})

    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://api.render.com", transport=httpx.MockTransport(handle)
    ) as client:
        if status == "live":
            deploy_image(client, "srv-controlled", IMAGE, report)
            assert report["platform"] == "live"
            assert "outcome" not in report  # Smoke is still required.
        else:
            with pytest.raises(RuntimeError, match="Render deployment failed"):
                deploy_image(client, "srv-controlled", IMAGE, report)
            assert "platform" not in report
    assert json.loads(calls[0].content) == {"imageUrl": IMAGE}
    assert str(calls[1].url).endswith("/srv-controlled/deploys/dep-controlled")
    assert len(calls) == 2


def test_render_does_not_resubmit_an_uncertain_deployment() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("lost acknowledgement")

    with httpx.Client(
        base_url="https://api.render.com", transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(httpx.ReadTimeout):
            deploy_image(client, "srv-controlled", IMAGE, {})
    assert len(calls) == 1


@pytest.mark.parametrize(
    "failure", ["", "replace", "cleanup", "wrong_service", "bad_token"]
)
def test_delivery_records_success_only_after_smoke_and_cleanup(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import deploy_render

    evidence = tmp_path / "delivery.json"
    monkeypatch.setattr(
        "sys.argv", ["deploy", "--image", IMAGE, "--evidence", str(evidence)]
    )
    for name, value in {
        "RENDER_SERVICE_ID": "srv-controlled",
        "RENDER_API_KEY": "secret-render-token",
        "CALENDAR_API_TOKEN": "secret-calendar-token" * 2,
        "CALENDAR_BASE_URL": "https://calendar.example",
    }.items():
        monkeypatch.setenv(name, value)
    if failure == "bad_token":
        monkeypatch.setenv("CALENDAR_API_TOKEN", "short")
    original_client = httpx.Client
    calls: list[str] = []
    render_calls: list[str] = []

    def render_handler(request: httpx.Request) -> httpx.Response:
        render_calls.append(request.method)
        if request.url.path == "/v1/services/srv-controlled":
            return httpx.Response(
                200,
                json={
                    "serviceDetails": {
                        "url": "https://different.example"
                        if failure == "wrong_service"
                        else "https://calendar.example"
                    }
                },
            )
        if request.method == "POST":
            return httpx.Response(201, json={"id": "dep-controlled"})
        return httpx.Response(200, json={"status": "live"})

    def client_factory(**kwargs: object) -> httpx.Client:
        if kwargs["base_url"] == "https://api.render.com":
            return original_client(
                base_url="https://api.render.com",
                transport=httpx.MockTransport(render_handler),
            )
        return original_client(
            base_url="https://calendar.example",
            transport=calendar_transport(calls, failure=failure),
        )

    monkeypatch.setattr(deploy_render.httpx, "Client", client_factory)
    if failure:
        with pytest.raises(SystemExit, match="Delivery failed"):
            main()
    else:
        main()
    result = json.loads(evidence.read_text())
    assert result["outcome"] == ("failed" if failure else "successful")
    assert result["image"] == IMAGE
    if failure in ("wrong_service", "bad_token"):
        assert "deploy_id" not in result
        assert "POST" not in render_calls
        assert not calls
        assert result["cleanup"] == "not_started"
    else:
        assert result["deploy_id"] == "dep-controlled"
        assert result["cleanup"] == ("failed" if failure == "cleanup" else "confirmed")
    retained = evidence.read_text() + evidence.with_suffix(".yaml").read_text()
    captured = capsys.readouterr()
    for private in (
        "secret-render-token",
        "secret-calendar-token",
        "owned-event",
        "OSPSD delivery smoke",
    ):
        assert private not in retained + captured.out + captured.err

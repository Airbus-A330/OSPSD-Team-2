"""Prove delivery failure gates and disposable smoke cleanup without credentials."""

import json
from pathlib import Path
import re

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
@pytest.mark.parametrize("acknowledgment", [201, 202])
def test_render_waits_for_the_requested_digest_deployment(
    status: str,
    acknowledgment: int,
) -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(acknowledgment, json={"id": "dep-controlled"})
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
            assert report["platform"] == "accepted"
    requested = json.loads(calls[0].content)["imageUrl"]
    assert re.fullmatch(
        "ghcr.io/airbus-a330/ospsd-team-2:delivery-[0-9a-f]{32}@sha256:" + "a" * 64,
        requested,
    )
    assert report["request_image"] == requested
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


def test_render_retries_with_digest_when_tagged_digest_is_rejected() -> None:
    submitted: list[str] = []
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            submitted.append(json.loads(request.content)["imageUrl"])
            if len(submitted) == 1:
                return httpx.Response(400, json={"message": "invalid imageUrl"})
            return httpx.Response(201, json={"id": "dep-controlled"})
        return httpx.Response(200, json={"status": "live"})

    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://api.render.com", transport=httpx.MockTransport(handle)
    ) as client:
        deploy_image(client, "srv-controlled", IMAGE, report)
    assert len(submitted) == 2
    assert submitted[0].startswith("ghcr.io/airbus-a330/ospsd-team-2:delivery-")
    assert submitted[0].endswith("@" + IMAGE.split("@")[1])
    assert submitted[1] == IMAGE
    assert report["request_image"] == IMAGE
    assert str(calls[-1].url).endswith("/srv-controlled/deploys/dep-controlled")


@pytest.mark.parametrize("final_status", ["live", "update_failed"])
def test_empty_queued_response_resolves_exact_request_and_monitors_it(
    monkeypatch: pytest.MonkeyPatch,
    final_status: str,
) -> None:
    from scripts import deploy_render

    monkeypatch.setattr(deploy_render.time, "sleep", lambda _: None)
    submitted: list[str] = []
    polled: list[str] = []
    listings = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal listings
        if request.method == "POST":
            submitted.append(json.loads(request.content)["imageUrl"])
            return httpx.Response(202)  # Render may return no deployment object.
        if request.url.path.endswith("/deploys"):
            listings += 1
            # Neither an old live release nor a concurrent deployment of the
            # same digest is evidence that this request has become live.
            rows = [
                {
                    "deploy": {
                        "id": "dep-old",
                        "image": {"ref": IMAGE},
                        "status": "live",
                    }
                },
                {
                    "deploy": {
                        "id": "dep-other",
                        "image": {"ref": IMAGE.replace("@", ":other@")},
                        "status": "live",
                    }
                },
            ]
            if listings > 1:
                rows.append(
                    {
                        "deploy": {
                            "id": "dep-ours",
                            "image": {"ref": submitted[0]},
                            "status": "queued",
                        }
                    }
                )
            return httpx.Response(200, json=rows)
        polled.append(request.url.path)
        return httpx.Response(
            200, json={"status": "queued" if len(polled) == 1 else final_status}
        )

    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://api.render.com", transport=httpx.MockTransport(handle)
    ) as client:
        if final_status == "live":
            deploy_image(client, "srv-controlled", IMAGE, report)
        else:
            with pytest.raises(RuntimeError, match="Render deployment failed"):
                deploy_image(client, "srv-controlled", IMAGE, report)
    assert len(submitted) == 1
    assert submitted[0].startswith("ghcr.io/airbus-a330/ospsd-team-2:delivery-")
    assert submitted[0].endswith("@" + IMAGE.split("@")[1])
    assert listings == 2
    assert polled == ["/v1/services/srv-controlled/deploys/dep-ours"] * 2
    assert report["deploy_id"] == "dep-ours"
    assert report["platform"] == ("live" if final_status == "live" else "accepted")
    assert "outcome" not in report  # Full delivery must still smoke and clean up.


@pytest.mark.parametrize("ambiguous", [False, True])
def test_queued_discovery_checks_all_pages_before_selecting_a_match(
    ambiguous: bool,
) -> None:
    submitted: list[str] = []
    queries: list[dict[str, str]] = []
    polled: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            submitted.append(json.loads(request.content)["imageUrl"])
            return httpx.Response(202)
        if request.url.path.endswith("/deploys"):
            cursor = request.url.params.get("cursor")
            queries.append(dict(request.url.params))
            if not cursor:
                rows: list[dict[str, object]] = [
                    {"deploy": {"id": f"dep-old{i}"}, "cursor": f"cursor{i}"}
                    for i in range(100)
                ]
                rows[0]["deploy"] = {"id": "dep-ours", "image": {"ref": submitted[0]}}
                return httpx.Response(200, json=rows)
            return httpx.Response(
                200,
                json=[
                    {"deploy": {"id": "dep-duplicate", "image": {"ref": submitted[0]}}}
                ]
                if ambiguous
                else [],
            )
        polled.append(request.url.path)
        return httpx.Response(200, json={"status": "live"})

    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://api.render.com", transport=httpx.MockTransport(handle)
    ) as client:
        if ambiguous:
            with pytest.raises(
                RuntimeError, match="Ambiguous queued deployment identity"
            ):
                deploy_image(client, "srv-controlled", IMAGE, report)
            assert report["candidate_deploy_ids"] == ["dep-duplicate", "dep-ours"]
            assert "deploy_id" not in report
            assert not polled
        else:
            deploy_image(client, "srv-controlled", IMAGE, report)
            assert report["deploy_id"] == "dep-ours"
            assert polled == ["/v1/services/srv-controlled/deploys/dep-ours"]
    assert queries == [
        {"limit": "100"},
        {"limit": "100", "cursor": "cursor99"},
    ]
    assert len(submitted) == 1


@pytest.mark.parametrize("body", [b"", b"Queued", b"{}", b"null"])
def test_unresolved_queued_request_times_out_without_resubmission_or_wrong_smoke(
    body: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import deploy_render

    ticks = iter([0, 1, 2, 901])
    monkeypatch.setattr(deploy_render.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(deploy_render.time, "sleep", lambda _: None)
    methods: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(202, content=body)
        # A normalized reference or an earlier live deployment of the digest
        # cannot prove which request was queued; retain reconciliation evidence.
        return httpx.Response(
            200,
            json=[
                {"deploy": {"id": "dep-old", "image": {"ref": IMAGE}, "status": "live"}}
            ],
        )

    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://api.render.com", transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(RuntimeError, match="Queued deployment discovery timed out"):
            deploy_image(client, "srv-controlled", IMAGE, report)
    assert methods == ["POST", "GET"]
    assert report["reconciliation_required"] is True
    assert report["deployment_tracking"] == "awaiting_id"
    assert str(report["request_image"]).endswith("@" + IMAGE.split("@")[1])
    assert "deploy_id" not in report
    assert report["platform"] == "accepted"


@pytest.mark.parametrize(
    "failure", ["", "replace", "cleanup", "wrong_service", "bad_token"]
)
@pytest.mark.parametrize("acknowledgment", [201, 202])
def test_delivery_records_success_only_after_smoke_and_cleanup(
    failure: str,
    acknowledgment: int,
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
    submitted: list[str] = []

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
            submitted.append(json.loads(request.content)["imageUrl"])
            if acknowledgment == 202:
                return httpx.Response(202)
            return httpx.Response(201, json={"id": "dep-controlled"})
        if request.url.path.endswith("/deploys"):
            return httpx.Response(
                200,
                json=[
                    {"deploy": {"id": "dep-controlled", "image": {"ref": submitted[0]}}}
                ],
            )
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
    assert result.get("reconciliation_required", False) is bool(
        failure in ("replace", "cleanup")
    )
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

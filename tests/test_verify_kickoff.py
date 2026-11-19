"""Verify hosted acceptance checks without external credentials or writes."""

import json

import httpx
import pytest

from app.controlled_workflow import controlled_workflow
from app.workflows import ProjectKickoffRequest, StepName, WorkflowFailure
from scripts.verify_kickoff import verify_kickoff


@pytest.mark.parametrize("failure", ["", "lost_write", "bad_result", "setup"])
def test_happy_check_never_retries_or_claims_provider_confirmation(
    failure: str,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200)
        if failure == "lost_write":
            raise httpx.ReadTimeout("secret-provider-detail")
        if failure == "setup":
            return httpx.Response(503, text="secret-provider-detail")
        payload = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "calendar": {
                    "outcome": "succeeded",
                    "event": {"id": "private-event", **payload["event"]},
                },
                "storage": {
                    "outcome": "succeeded",
                    "document": {
                        "id": "private-file",
                        "path": payload["document_path"],
                    },
                },
                "issue_tracker": {
                    "outcome": "succeeded",
                    "issue": {
                        "id": "private-card",
                        "title": "wrong"
                        if failure == "bad_result"
                        else payload["issue_title"],
                    },
                },
            },
        )

    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    ) as client:
        if failure:
            with pytest.raises((httpx.HTTPError, RuntimeError)):
                verify_kickoff(client, report)
        else:
            verify_kickoff(client, report)
    assert calls == ["GET", "POST"]
    assert report["outcome"] == ("failed" if failure else "passed")
    assert report["direct_provider_verification"] == "pending"
    assert report["cleanup"] == (
        "reconciliation_required" if failure else "retained_for_provider_inspection"
    )
    for secret in (
        "secret-provider-detail",
        "private-event",
        "private-file",
        "private-card",
    ):
        assert secret not in json.dumps(report)


@pytest.mark.parametrize("step", ["calendar", "storage", "issue_tracker"])
def test_controlled_failure_checks_actual_partial_progress(step: StepName) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200)
        body = ProjectKickoffRequest.model_validate_json(request.content)
        try:
            controlled_workflow(step).run(body)
        except WorkflowFailure as failure:
            return httpx.Response(403, json=failure.result().model_dump(mode="json"))
        raise AssertionError("Expected controlled rejection")

    report: dict[str, object] = {}
    with httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    ) as client:
        verify_kickoff(client, report, expected_failure=step)
    assert report["outcome"] == "passed"
    assert report["failed_step"] == step
    assert report["direct_provider_verification"] == "not_applicable_synthetic"


def test_plain_auth_denial_does_not_pass_as_controlled_failure() -> None:
    report: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200)
            if request.method == "GET"
            else httpx.Response(
                403,
                json={
                    "error": {
                        "code": "access_denied",
                        "message": "Deployment access denied",
                        "retryable": False,
                    }
                },
            )
        )

    with httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(ValueError):
            verify_kickoff(client, report, expected_failure="storage")
    assert report["outcome"] == "failed"


def test_cli_retains_sanitized_failure_without_overwriting_previous_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import verify_kickoff as module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["verify", "--allow-create"])
    monkeypatch.setenv("CALENDAR_BASE_URL", "https://example.test")
    monkeypatch.setenv("CALENDAR_API_TOKEN", "private-token-" + "x" * 32)
    original = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200)
        raise httpx.ReadTimeout("private-provider-body-and-key", request=request)

    def factory(**kwargs: object) -> httpx.Client:
        return original(
            base_url="https://example.test", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(module.httpx, "Client", factory)
    for _ in range(2):
        with pytest.raises(SystemExit) as caught:
            module.main()
        assert "private" not in str(caught.value)
    paths = list((tmp_path / ".runtime").glob("kickoff-*/verification.json"))
    assert len(paths) == 2
    for path in paths:
        report = json.loads(path.read_text())
        assert report["outcome"] == "failed"
        assert report["stage"] == "workflow_request"
        assert report["cleanup"] == "reconciliation_required"
        assert "http_status" not in report
        assert report["marker"].startswith("ospsd-kickoff-")
        assert "private" not in path.read_text()
    output = capsys.readouterr()
    assert "private" not in output.out + output.err

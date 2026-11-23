"""Exercise native browser forms through UI -> HTTP client -> actual Team 2 API."""

import httpx
import pytest
from fastapi.testclient import TestClient

from interface.clients import AgentView, Decision, HTTPWorkflowClient
from interface.tests.support import FORM, FakeAccount, FakeAgent, Inputs, controlled_api
from interface.web import create_app


def client_for(
    failure: str = "", uncertain: bool = False
) -> tuple[TestClient, list[str]]:
    api, calls = controlled_api(failure, uncertain)
    ui = create_app(
        HTTPWorkflowClient(
            "http://127.0.0.1:8000", transport=httpx.ASGITransport(app=api)
        )
    )
    return TestClient(ui), calls


def post(client: TestClient, action: str, **values: str) -> httpx.Response:
    csrf = Inputs(client.get("/").text).values["csrf"]
    return client.post("/action", data={"csrf": csrf, "action": action, **values})


def review(client: TestClient) -> str:
    response = post(client, "review", **FORM)
    assert response.status_code == 200
    return Inputs(response.text).values["review_id"]


def test_manual_scenario_requires_review_then_returns_all_results() -> None:
    client, calls = client_for()
    token = review(client)
    assert calls == []
    preview = client.get("/").text
    for value in FORM.values():
        assert value in preview
    response = post(client, "execute", review_id=token)
    assert response.status_code == 200
    assert calls == ["storage", "issue_tracker", "calendar"]
    for value in (
        "Your kickoff is ready",
        "controlled-document",
        "controlled-issue",
        "controlled-event",
    ):
        assert value in response.text


def test_reject_sends_no_request_and_retains_editable_inputs() -> None:
    client, calls = client_for()
    response = post(client, "reject", review_id=review(client))
    assert "Nothing was sent to the API" in response.text
    assert FORM["title"] in response.text
    assert calls == []


@pytest.mark.parametrize(
    "failure,expected_calls,state",
    [
        ("storage", ["storage"], "Failed"),
        ("issue_tracker", ["storage", "issue_tracker"], "Partially succeeded"),
        ("calendar", ["storage", "issue_tracker", "calendar"], "Partially succeeded"),
    ],
)
def test_controlled_failures_show_confirmed_progress(
    failure: str, expected_calls: list[str], state: str
) -> None:
    client, calls = client_for(failure)
    response = post(client, "execute", review_id=review(client))
    assert state in response.text
    assert "access_denied" in response.text
    assert "account owner" in response.text
    if failure != "storage":
        assert "controlled-document" in response.text
        assert "not rolled back" in response.text
    if failure != "calendar":
        assert "Not attempted" in response.text
    assert calls == expected_calls


def test_uncertain_result_is_visible_without_replay() -> None:
    client, calls = client_for("calendar", True)
    token = review(client)
    response = post(client, "execute", review_id=token)
    assert "Uncertain" in response.text
    assert "controlled-document" in response.text
    assert "controlled-issue" in response.text
    assert "Do not replay" in response.text
    assert post(client, "execute", review_id=token).status_code == 409
    assert client.get("/").status_code == 200
    assert calls == ["storage", "issue_tracker", "calendar"]


def test_stale_review_cannot_submit_changed_values() -> None:
    client, calls = client_for()
    token = review(client)
    response = post(client, "review", **{**FORM, "title": "Changed title"})
    assert post(client, "execute", review_id=token).status_code == 409
    assert calls == []
    new_token = Inputs(response.text).values["review_id"]
    result = post(client, "execute", review_id=new_token, title="Tampered title")
    assert "Changed title" in result.text
    assert "Tampered title" not in result.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "   "),
        ("start", "tomorrow"),
        ("document_path", "/../bad"),
        ("issue_title", ""),
    ],
)
def test_invalid_input_is_visible_without_provider_calls(
    field: str, value: str
) -> None:
    client, calls = client_for()
    response = post(client, "review", **{**FORM, field: value})
    assert "Check these fields" in response.text
    assert "Confirm and create" not in response.text
    assert calls == []


@pytest.mark.parametrize("csrf", ["", "wrong", "非ASCII"])
def test_csrf_rejected(csrf: str) -> None:
    client, calls = client_for()
    client.get("/")
    assert (
        client.post(
            "/action", data={"csrf": csrf, "action": "review", **FORM}
        ).status_code
        == 403
    )
    assert calls == []


def test_session_isolation_and_restart_reject_old_reviews() -> None:
    client, calls = client_for()
    token = review(client)
    other = TestClient(client.app)
    assert FORM["title"] not in other.get("/").text
    assert post(other, "execute", review_id=token).status_code == 409
    restarted, _ = client_for()
    restarted.cookies.update(client.cookies)
    assert (
        restarted.post(
            "/action", data={"action": "execute", "review_id": token}
        ).status_code
        == 409
    )
    assert calls == []


def test_html_is_escaped_and_security_headers_are_set() -> None:
    client, _ = client_for()
    response = post(
        client, "review", **{**FORM, "document_content": "<script>alert('x')</script>"}
    )
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_unfinished_services_are_explicit_and_fail_closed() -> None:
    client, calls = client_for()
    page = client.get("/").text
    assert "Natural-language help is not connected yet" in page
    assert "status is unknown" in page
    assert post(client, "agent_submit", message="hello").status_code == 503
    assert post(client, "sign_in").status_code == 503
    assert calls == []


@pytest.mark.parametrize(
    "action,expected",
    [("approve", "approve"), ("reject_proposal", "reject"), ("change", "change")],
)
def test_agent_decisions_bind_exact_proposal_revision(
    action: str, expected: str
) -> None:
    agent = FakeAgent()
    client = TestClient(create_app(agent_factory=lambda: agent))
    preview = post(client, "agent_submit", message="Change the meeting")
    assert "Team calendar / event-123" in preview.text
    assert "Old title" in preview.text and "New title" in preview.text
    assert "<script>bad()" not in preview.text
    assert agent.decisions == []
    assert (
        post(client, "approve", proposal_id="proposal-1", revision="wrong").status_code
        == 409
    )
    response = post(
        client,
        action,
        proposal_id="proposal-1",
        revision="rev-1",
        clarification="Use tomorrow",
    )
    assert response.status_code == 200
    assert agent.decisions == [
        ("run-1", "proposal-1", "rev-1", expected, "Use tomorrow")
    ]
    assert (
        post(client, "approve", proposal_id="proposal-1", revision="rev-1").status_code
        == 409
    )


def test_account_controls_use_adapter_reported_status() -> None:
    account = FakeAccount()
    client = TestClient(create_app(account_factory=lambda: account))
    assert "Signed out" in post(client, "account_status").text
    assert "Signed in" in post(client, "sign_in").text
    assert "attention" in client.get("/").text
    assert post(client, "disconnect", provider="Unknown").status_code == 409
    assert "disconnected" in post(client, "disconnect", provider="Calendar").text
    assert account.actions == [("sign_in", ""), ("disconnect", "Calendar")]


def test_lost_agent_decision_disables_approval_until_service_refresh() -> None:
    class LostDecisionAgent(FakeAgent):
        async def decide(
            self,
            run_id: str,
            proposal_id: str,
            revision: str,
            decision: Decision,
            clarification: str,
        ) -> AgentView:
            self.decisions.append(
                (run_id, proposal_id, revision, decision, clarification)
            )
            raise httpx.ReadTimeout("private service detail")

    agent = LostDecisionAgent()
    client = TestClient(create_app(agent_factory=lambda: agent))
    post(client, "agent_submit", message="Update meeting")
    response = post(client, "approve", proposal_id="proposal-1", revision="rev-1")
    assert "Uncertain" in response.text
    assert "do not approve again" in response.text
    assert "private service detail" not in response.text
    assert "Approve this exact version" not in response.text
    assert (
        post(client, "approve", proposal_id="proposal-1", revision="rev-1").status_code
        == 409
    )
    assert len(agent.decisions) == 1


def test_lost_workflow_http_response_remains_uncertain_after_refresh() -> None:
    calls: list[httpx.Request] = []

    def lose_response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("private connection detail")

    client = TestClient(
        create_app(
            HTTPWorkflowClient(
                "http://127.0.0.1:8002", transport=httpx.MockTransport(lose_response)
            )
        )
    )
    token = review(client)
    response = post(client, "execute", review_id=token)
    assert "Uncertain" in response.text
    assert "Do not submit again" in response.text
    assert FORM["document_path"] in response.text
    assert "Uncertain" in client.get("/").text
    assert "private connection detail" not in response.text
    assert post(client, "execute", review_id=token).status_code == 409
    assert len(calls) == 1


def test_local_preview_rejects_untrusted_host() -> None:
    client, _ = client_for()
    assert client.get("/", headers={"Host": "untrusted.example"}).status_code == 400


def test_demo_is_visibly_labeled_as_synthetic() -> None:
    client = TestClient(
        create_app(demo=True, agent_factory=FakeAgent, account_factory=FakeAccount)
    )
    assert (
        "all records, agent responses, and account states are synthetic"
        in client.get("/").text
    )


def test_refresh_does_not_post_another_workflow() -> None:
    client, calls = client_for()
    token = review(client)
    post(client, "execute", review_id=token)
    client.get("/")
    client.get("/")
    assert calls == ["storage", "issue_tracker", "calendar"]

"""Controlled service adapters and browser-form helpers for interface tests."""

from dataclasses import dataclass
from html.parser import HTMLParser

from calendar_contract import CreateEvent, Event
from fastapi import FastAPI

from app.errors import PermissionDeniedError, ProviderFailureError
from app.main import create_app
from app.workflow_composition import get_project_kickoff_workflow
from app.workflows import DocumentResult, IssueResult, ProjectKickoffWorkflow
from interface.clients import (
    AccountView,
    AgentView,
    ConnectionView,
    Decision,
    Proposal,
    ProposedChange,
)

FORM = {
    "title": "  Project kickoff  ",
    "start": "2030-01-15T10:00:00-05:00",
    "end": "2030-01-15T10:30:00-05:00",
    "document_path": "/projects/alpha/kickoff.md",
    "document_content": "Agenda\nDiscuss next steps",
    "issue_title": "Follow up",
}


class Inputs(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.values: dict[str, str] = {}
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "input" and data.get("name"):
            self.values[str(data["name"])] = data.get("value") or ""


@dataclass
class ControlledVerticals:
    """Only the true provider boundaries are replaced in API integration tests."""

    calls: list[str]
    failure: str = ""
    uncertain: bool = False

    def check(self, step: str) -> None:
        self.calls.append(step)
        if self.failure == step:
            if self.uncertain:
                raise ProviderFailureError("Synthetic unconfirmed write")
            raise PermissionDeniedError("Synthetic access rejection")

    def create(self, request: CreateEvent) -> Event:
        self.check("calendar")
        return Event(id="controlled-event", **request.model_dump())

    def create_issue(self, title: str) -> IssueResult:
        self.check("issue_tracker")
        return IssueResult(id="controlled-issue", title=title)


@dataclass
class ControlledDocuments:
    verticals: ControlledVerticals

    def create(self, path: str, content: bytes) -> DocumentResult:
        self.verticals.check("storage")
        return DocumentResult(id="controlled-document", path=path)


def controlled_api(
    failure: str = "", uncertain: bool = False
) -> tuple[FastAPI, list[str]]:
    calls: list[str] = []
    verticals = ControlledVerticals(calls, failure, uncertain)
    workflow = ProjectKickoffWorkflow(
        verticals, ControlledDocuments(verticals), verticals
    )
    app = create_app()
    app.dependency_overrides[get_project_kickoff_workflow] = lambda: workflow
    return app, calls


class FakeAgent:
    """Provisional service adapter, never selected by production configuration."""

    def __init__(self) -> None:
        self.decisions: list[tuple[str, str, str, Decision, str]] = []
        self.view = AgentView(
            "run-1",
            "awaiting approval",
            "Review this change.",
            Proposal(
                "proposal-1",
                "rev-1",
                (
                    ProposedChange(
                        "update",
                        "Calendar",
                        "Team calendar / event-123",
                        {"title": "Old title"},
                        {"title": "New title <script>bad()</script>"},
                    ),
                ),
            ),
            can_request_change=True,
        )

    async def submit(self, message: str) -> AgentView:
        return self.view

    async def refresh(self, run_id: str) -> AgentView:
        return self.view

    async def decide(
        self,
        run_id: str,
        proposal_id: str,
        revision: str,
        decision: Decision,
        clarification: str,
    ) -> AgentView:
        self.decisions.append((run_id, proposal_id, revision, decision, clarification))
        self.view = AgentView(
            run_id,
            "preparing" if decision == "change" else "succeeded",
            f"Decision recorded: {decision}",
        )
        return self.view


class FakeAccount:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []
        self.view = AccountView(False, "Test account")

    async def status(self) -> AccountView:
        return self.view

    async def act(self, action: str, provider: str) -> AccountView:
        self.actions.append((action, provider))
        self.view = AccountView(
            True,
            "Test user",
            (
                ConnectionView(
                    "Calendar",
                    "disconnected" if action == "disconnect" else "attention",
                    "Reconnect required",
                ),
            ),
        )
        return self.view

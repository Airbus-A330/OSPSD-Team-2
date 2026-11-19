"""Explicitly synthetic workflow dependencies for credential-free failure checks."""

from dataclasses import dataclass

from calendar_contract import CreateEvent, Event

from app.errors import PermissionDeniedError
from app.workflows import DocumentResult, IssueResult, ProjectKickoffWorkflow, StepName


@dataclass(frozen=True)
class ControlledCalendar:
    """Return a synthetic event or a known pre-write rejection."""

    fail_step: StepName

    def create(self, request: CreateEvent) -> Event:
        if self.fail_step == "calendar":
            raise PermissionDeniedError("Controlled Calendar rejection")
        return Event(id="controlled-event", **request.model_dump())


@dataclass(frozen=True)
class ControlledStorage:
    """Return a synthetic document reference or a known pre-write rejection."""

    fail_step: StepName

    def create(self, path: str, content: bytes) -> DocumentResult:
        if self.fail_step == "storage":
            raise PermissionDeniedError("Controlled storage rejection")
        return DocumentResult(id="controlled-document", path=path)


@dataclass(frozen=True)
class ControlledIssues:
    """Return a synthetic issue reference or a known pre-write rejection."""

    fail_step: StepName

    def create_issue(self, title: str) -> IssueResult:
        if self.fail_step == "issue_tracker":
            raise PermissionDeniedError("Controlled Issue Tracker rejection")
        return IssueResult(id="controlled-issue", title=title)


def controlled_workflow(fail_step: StepName) -> ProjectKickoffWorkflow:
    """Build only explicitly requested synthetic dependencies; never contact providers."""
    return ProjectKickoffWorkflow(
        ControlledCalendar(fail_step),
        ControlledStorage(fail_step),
        ControlledIssues(fail_step),
    )

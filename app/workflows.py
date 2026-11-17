"""Provider-independent fixed workflows composed from vertical capabilities."""

from dataclasses import dataclass
from typing import Literal, Protocol

from calendar_contract import CreateEvent, Event
from pydantic import BaseModel, ConfigDict, Field, StrictStr


class CalendarCreator(Protocol):
    """Calendar capability required by the project-kickoff workflow."""

    def create(self, request: CreateEvent) -> Event:
        """Create and return one calendar event."""


class StoredFile(Protocol):
    """Storage result fields used by the combined response."""

    id: str | None
    path: str


class DocumentCreator(Protocol):
    """Document-storage capability required by the workflow."""

    def create(self, path: str, content: bytes) -> StoredFile:
        """Create and return one stored document."""


class TrackedIssue(Protocol):
    """Issue result fields used by the combined response."""

    id: str
    title: str


class IssueCreator(Protocol):
    """Issue-tracker capability required by the workflow."""

    def create_issue(self, title: str) -> TrackedIssue:
        """Create and return one issue."""


class ProjectKickoffRequest(BaseModel):
    """Inputs for the fixed event, document, and issue workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: CreateEvent
    document_path: StrictStr = Field(min_length=1, pattern=r"^/")
    document_content: StrictStr = Field(min_length=1)
    issue_title: StrictStr = Field(min_length=1, pattern=r"\S")


class CalendarStepResult(BaseModel):
    """Successful Calendar step result."""

    outcome: Literal["succeeded"] = "succeeded"
    event: Event


class DocumentResult(BaseModel):
    """Provider-independent stored-document reference."""

    id: str | None
    path: str


class DocumentStepResult(BaseModel):
    """Successful Cloud Storage step result."""

    outcome: Literal["succeeded"] = "succeeded"
    document: DocumentResult


class IssueResult(BaseModel):
    """Provider-independent issue reference."""

    id: str
    title: str


class IssueStepResult(BaseModel):
    """Successful Issue Tracker step result."""

    outcome: Literal["succeeded"] = "succeeded"
    issue: IssueResult


class ProjectKickoffResult(BaseModel):
    """Combined successful result of all three fixed workflow steps."""

    calendar: CalendarStepResult
    storage: DocumentStepResult
    issue_tracker: IssueStepResult


@dataclass(frozen=True)
class ProjectKickoffWorkflow:
    """Run the fixed Calendar, Storage, then Issue Tracker workflow."""

    calendar: CalendarCreator
    storage: DocumentCreator
    issues: IssueCreator

    def run(self, request: ProjectKickoffRequest) -> ProjectKickoffResult:
        """Execute each write once, in the documented fixed order."""
        event = self.calendar.create(request.event)
        document = self.storage.create(
            request.document_path,
            request.document_content.encode("utf-8"),
        )
        issue = self.issues.create_issue(request.issue_title)
        return ProjectKickoffResult(
            calendar=CalendarStepResult(event=event),
            storage=DocumentStepResult(
                document=DocumentResult(id=document.id, path=document.path)
            ),
            issue_tracker=IssueStepResult(
                issue=IssueResult(id=issue.id, title=issue.title)
            ),
        )

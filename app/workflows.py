"""Provider-independent fixed workflows composed from vertical capabilities."""

from dataclasses import dataclass
from typing import Literal, Protocol

from calendar_contract import CalendarError, CreateEvent, ErrorCode, Event
from issue_tracker_contract.models import MAX_TITLE_LENGTH
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.errors import ProviderFailureError, ServiceError, StorageConflictError

StepName = Literal["calendar", "storage", "issue_tracker"]
FailureStep = Literal["calendar", "storage", "issue_tracker", "configuration"]
FailureStage = Literal["setup", "operation"]
WorkflowErrorCode = ErrorCode | Literal["conflict"]

# Team 3's selected implementation uses Dropbox's documented single-upload
# ceiling. Validate the encoded payload before any workflow dependency is built.
MAX_DOCUMENT_CONTENT_BYTES = 150_000_000


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
    issue_title: StrictStr = Field(
        min_length=1, max_length=MAX_TITLE_LENGTH, pattern=r"\S"
    )

    @field_validator("document_path")
    @classmethod
    def validate_document_path(cls, value: str) -> str:
        """Require the portable absolute path shape used by the shared contract."""
        if value == "/" or any(
            segment in {"", ".", ".."} for segment in value[1:].split("/")
        ):
            raise ValueError("Document path contains an invalid segment")
        return value

    @field_validator("document_content")
    @classmethod
    def validate_document_content(cls, value: str) -> str:
        """Enforce the selected implementation's byte limit before any write."""
        if len(value.encode("utf-8")) > MAX_DOCUMENT_CONTENT_BYTES:
            raise ValueError("Document content exceeds the 150 MB limit")
        return value


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


class IncompleteStepResult(BaseModel):
    """An unattempted write, a known rejection, or an uncertain write outcome."""

    outcome: Literal["not_attempted", "failed", "uncertain"] = "not_attempted"


class WorkflowProgress(BaseModel):
    """Confirmed results and incomplete states for this execution only."""

    calendar: CalendarStepResult | IncompleteStepResult = Field(
        default_factory=IncompleteStepResult
    )
    storage: DocumentStepResult | IncompleteStepResult = Field(
        default_factory=IncompleteStepResult
    )
    issue_tracker: IssueStepResult | IncompleteStepResult = Field(
        default_factory=IncompleteStepResult
    )


class WorkflowErrorBody(BaseModel):
    """Existing shared error fields without dependency exception details."""

    code: WorkflowErrorCode
    message: str
    retryable: bool


class WorkflowErrorResponse(BaseModel):
    """Workflow request errors before a particular step can be attempted."""

    error: WorkflowErrorBody


class ProjectKickoffFailureResult(WorkflowErrorResponse):
    """Step-aware error extension used only by the composition endpoint."""

    failed_step: FailureStep
    failure_stage: FailureStage
    steps: WorkflowProgress


class WorkflowFailure(ServiceError):
    """Preserve progress while sanitizing expected and unexpected boundary errors."""

    def __init__(
        self,
        step: FailureStep,
        error: Exception,
        progress: WorkflowProgress | None = None,
        *,
        stage: FailureStage = "operation",
    ) -> None:
        cause = error if isinstance(error, CalendarError) else ProviderFailureError()
        conflict = error if isinstance(error, StorageConflictError) else None
        message = (
            conflict.public_message
            if conflict is not None and conflict.public_message is not None
            else f"Workflow {step} {stage} failed"
        )
        super().__init__(
            message,
            code=cause.code,
            retryable=cause.retryable if stage == "setup" else False,
        )
        self.public_code: WorkflowErrorCode = (
            "conflict" if conflict is not None else self.code
        )
        self.failed_step = step
        self.failure_stage = stage
        self.unexpected = not isinstance(error, CalendarError)
        self.steps = progress if progress is not None else WorkflowProgress()
        if stage == "operation":
            outcome: Literal["uncertain", "failed"] = (
                "uncertain"
                if cause.code
                in {ErrorCode.PROVIDER_ERROR, ErrorCode.PROVIDER_UNAVAILABLE}
                else "failed"
            )
            self.steps = self.steps.model_copy(
                update={step: IncompleteStepResult(outcome=outcome)}
            )

    def result(self) -> ProjectKickoffFailureResult:
        """Return safe public metadata; never include underlying error text/details."""
        return ProjectKickoffFailureResult(
            error=WorkflowErrorBody(
                code=self.public_code, message=self.message, retryable=self.retryable
            ),
            failed_step=self.failed_step,
            failure_stage=self.failure_stage,
            steps=self.steps,
        )


@dataclass(frozen=True)
class ProjectKickoffWorkflow:
    """Run the fixed Storage, Issue Tracker, then Calendar workflow."""

    calendar: CalendarCreator
    storage: DocumentCreator
    issues: IssueCreator

    def run(self, request: ProjectKickoffRequest) -> ProjectKickoffResult:
        """Execute once; boundary/model failures retain progress and never replay writes.

        Broad catches are restricted to individual vertical calls and their result
        validation: unexpected errors can also follow committed writes. Neither
        exception text nor provider details are copied to the public error.
        """
        progress = WorkflowProgress()
        try:
            document = self.storage.create(
                request.document_path, request.document_content.encode("utf-8")
            )
            storage = DocumentStepResult(
                document=DocumentResult(id=document.id, path=document.path)
            )
        except Exception as error:
            raise WorkflowFailure("storage", error, progress) from None
        progress.storage = storage
        try:
            issue = self.issues.create_issue(request.issue_title)
            issues = IssueStepResult(issue=IssueResult(id=issue.id, title=issue.title))
        except Exception as error:
            raise WorkflowFailure("issue_tracker", error, progress) from None
        progress.issue_tracker = issues
        try:
            calendar = CalendarStepResult(event=self.calendar.create(request.event))
        except Exception as error:
            raise WorkflowFailure("calendar", error, progress) from None
        progress.calendar = calendar
        return ProjectKickoffResult(
            calendar=calendar, storage=storage, issue_tracker=issues
        )

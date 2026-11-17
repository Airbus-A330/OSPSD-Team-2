"""Configuration, preflight and resource ownership for the fixed workflow."""

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from typing import TypeVar, cast

from cloud_storage_api import DocumentStorage, FileInfo

from app.composition import open_calendar_service
from app.controlled_workflow import controlled_workflow
from app.errors import ProviderFailureError, ProviderUnavailableError
from app.storage import create_document
from app.storage_composition import get_document_storage
from app.workflows import (
    IssueCreator,
    ProjectKickoffRequest,
    ProjectKickoffWorkflow,
    StepName,
    WorkflowFailure,
)

T = TypeVar("T")


@dataclass(frozen=True)
class StorageCreator:
    """Adapt shared storage creation to the existing service-error boundary."""

    storage: DocumentStorage

    def create(self, path: str, content: bytes) -> FileInfo:
        return create_document(self.storage, path, content)


def open_issue_creator() -> AbstractContextManager[IssueCreator]:
    """Construction seam for #83's shared-contract adapter and client lifetime."""
    # shortcut: #83 has not supplied its factory; replace this seam when available.
    raise ProviderUnavailableError(
        "Issue Tracker implementation is not configured", provider_involved=False
    )


def _open_step(
    stack: ExitStack, step: StepName, factory: Callable[[], AbstractContextManager[T]]
) -> T:
    """Sanitize construction errors before any write; unwind acquired resources."""
    try:
        return stack.enter_context(factory())
    except Exception as error:
        # Construction can fail unexpectedly; preserve its step, not secret details.
        raise WorkflowFailure(step, error, stage="setup") from None


def get_project_kickoff_workflow(
    request: ProjectKickoffRequest,
) -> Iterator[ProjectKickoffWorkflow]:
    """Validate input before setup, then select a workflow without provider logic.

    FastAPI validates the request parameter before calling this dependency; it
    is intentionally not retained. Every constructor runs before the first write.
    Controlled mode is explicit verification only, never a production fallback.
    """
    mode = os.getenv("WORKFLOW_IMPLEMENTATION", "configured")
    fail_step = os.getenv("WORKFLOW_FAIL_STEP")
    if mode == "controlled" and fail_step in {"calendar", "storage", "issue_tracker"}:
        yield controlled_workflow(cast(StepName, fail_step))
        return
    if mode != "configured" or fail_step is not None:
        raise WorkflowFailure(
            "configuration",
            ProviderFailureError("Invalid workflow configuration"),
            stage="setup",
        )
    with ExitStack() as stack:
        # Missing #83 wiring must fail before auth/client setup in other verticals.
        issues = _open_step(stack, "issue_tracker", open_issue_creator)
        calendar = _open_step(stack, "calendar", open_calendar_service)
        storage = _open_step(
            stack, "storage", lambda: contextmanager(get_document_storage)()
        )
        yield ProjectKickoffWorkflow(calendar, StorageCreator(storage), issues)

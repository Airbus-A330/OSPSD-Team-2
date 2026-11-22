"""Storage failures use existing service codes without unsafe write retries."""

from unittest.mock import Mock

import pytest
from calendar_contract import ErrorCode
from cloud_storage_api import (
    ConflictError,
    DocumentStorage,
    FileInfo,
    FileTooLargeError,
    InvalidOperationError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    ProviderError,
    ProviderUnavailableError,
    StorageError,
)

from app.errors import ServiceError, StorageConflictError
from app.storage import StorageWriteUncertainError, create_document


def test_create_returns_the_shared_metadata() -> None:
    storage = Mock(spec=DocumentStorage)
    expected = FileInfo("id:one", "notes.md", "/notes.md", 5, None, "rev1", None)
    storage.create.return_value = expected

    assert create_document(storage, "/notes.md", b"notes") == expected
    storage.create.assert_called_once_with("/notes.md", b"notes")


@pytest.mark.parametrize(
    ("failure", "code", "uncertain"),
    [
        (InvalidRequestError, ErrorCode.INVALID_INPUT, False),
        (InvalidOperationError, ErrorCode.INVALID_INPUT, False),
        (FileTooLargeError, ErrorCode.INVALID_INPUT, False),
        (NotFoundError, ErrorCode.NOT_FOUND, False),
        (PermissionDeniedError, ErrorCode.ACCESS_DENIED, False),
        (ProviderError, ErrorCode.PROVIDER_ERROR, True),
        (ProviderUnavailableError, ErrorCode.PROVIDER_ERROR, True),
        (StorageError, ErrorCode.PROVIDER_ERROR, True),
    ],
)
def test_storage_errors_are_sanitized_and_never_retry_writes(
    failure: type[StorageError], code: ErrorCode, uncertain: bool
) -> None:
    storage = Mock(spec=DocumentStorage)
    storage.create.side_effect = failure("sensitive provider details")

    with pytest.raises(ServiceError) as caught:
        create_document(storage, "/notes.md", b"notes")

    assert caught.value.code is code
    assert caught.value.retryable is False
    assert isinstance(caught.value, StorageWriteUncertainError) is uncertain
    assert "sensitive" not in str(caught.value)
    assert caught.value.__suppress_context__
    storage.create.assert_called_once_with("/notes.md", b"notes")


def test_storage_conflict_remains_distinct_from_malformed_input() -> None:
    storage = Mock(spec=DocumentStorage)
    storage.create.side_effect = ConflictError("sensitive provider details")

    with pytest.raises(StorageConflictError) as caught:
        create_document(storage, "/notes.md", b"notes")

    assert caught.value.code is ErrorCode.INVALID_INPUT
    assert caught.value.retryable is False
    assert caught.value.public_message == (
        "Storage path already exists; inspect its metadata and content before retrying"
    )
    assert "sensitive" not in str(caught.value)
    storage.create.assert_called_once_with("/notes.md", b"notes")


def test_unexpected_programming_errors_propagate() -> None:
    storage = Mock(spec=DocumentStorage)
    storage.create.side_effect = RuntimeError("programming defect")

    with pytest.raises(RuntimeError, match="programming defect"):
        create_document(storage, "/notes.md", b"notes")

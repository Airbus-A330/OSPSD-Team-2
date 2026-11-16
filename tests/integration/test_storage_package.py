"""Installed Team 3 package through the shared contract, with a controlled SDK."""

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import dropbox  # type: ignore[import-untyped]
import pytest
import requests
from cloud_storage_api import DocumentStorage, FileInfo
from dropbox import exceptions, files
from dropbox_client_impl import DropboxAuthError
from fastapi import Depends
from fastapi.testclient import TestClient

from app import storage_composition
from app.errors import InvalidInputError, ProviderFailureError, ProviderUnavailableError
from app.main import create_app
from app.storage import StorageWriteUncertainError, create_document
from app.storage_composition import get_document_storage

PATH = "/hw3-notes.md"
CONTENT = b"# Meeting notes\nCalendar event: event-123\n"


def metadata() -> files.FileMetadata:
    return files.FileMetadata(
        name="hw3-notes.md",
        id="id:document123",
        path_lower=PATH,
        path_display=PATH,
        client_modified=datetime(2026, 11, 16, tzinfo=UTC),
        server_modified=datetime(2026, 11, 16, tzinfo=UTC),
        rev="0123456789",
        size=len(CONTENT),
    )


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> Mock:
    client = Mock(spec=dropbox.Dropbox)
    client.clone.return_value = client
    monkeypatch.setenv("STORAGE_IMPLEMENTATION", "team3")
    monkeypatch.setattr(storage_composition, "get_dropbox_client", lambda: client)
    return client


def test_configured_package_creates_and_downloads_exact_content(sdk: Mock) -> None:
    stored: dict[str, bytes] = {}

    def upload(content: bytes, path: str, **kwargs: object) -> files.FileMetadata:
        stored[path] = content
        assert kwargs == {
            "mode": files.WriteMode.add,
            "autorename": False,
            "strict_conflict": True,
        }
        return metadata()

    def download(*, download_path: str, path: str) -> files.FileMetadata:
        Path(download_path).write_bytes(stored[path])
        return metadata()

    sdk.files_upload.side_effect = upload
    sdk.files_download_to_file.side_effect = download
    with contextmanager(get_document_storage)() as storage:
        assert isinstance(storage, DocumentStorage)
        assert create_document(storage, PATH, CONTENT) == FileInfo(
            "id:document123",
            "hw3-notes.md",
            PATH,
            len(CONTENT),
            "2026-11-16T00:00:00Z",
            "0123456789",
            None,
        )
        assert storage.download(PATH) == CONTENT

    assert stored == {PATH: CONTENT}
    sdk.clone.assert_called_once_with(
        max_retries_on_error=0, max_retries_on_rate_limit=0
    )
    sdk.close.assert_called_once_with()


def test_lost_write_response_preserves_record_and_refuses_duplicate(sdk: Mock) -> None:
    stored: dict[str, bytes] = {}

    def upload(content: bytes, path: str, **kwargs: object) -> files.FileMetadata:
        if path in stored:
            raise exceptions.ApiError(
                "request-id",
                files.UploadError.path(
                    files.UploadWriteFailed(
                        reason=files.WriteError.conflict(files.WriteConflictError.file)
                    )
                ),
                None,
                None,
            )
        stored[path] = content
        raise requests.exceptions.ConnectionError("response lost after commit")

    sdk.files_upload.side_effect = upload
    with contextmanager(get_document_storage)() as storage:
        with pytest.raises(StorageWriteUncertainError) as caught:
            create_document(storage, PATH, CONTENT)
        assert caught.value.retryable is False
        assert sdk.files_upload.call_count == 1
        assert stored == {PATH: CONTENT}

        with pytest.raises(InvalidInputError, match="Storage path already exists"):
            create_document(storage, PATH, b"different content")

    assert stored == {PATH: CONTENT}
    assert sdk.files_upload.call_count == 2
    sdk.close.assert_called_once_with()


@pytest.mark.parametrize("path", ["", "/", "relative.md", "/a//b", "/a/../b", "/a/"])
def test_bad_document_path_does_not_reach_sdk(sdk: Mock, path: str) -> None:
    with contextmanager(get_document_storage)() as storage:
        with pytest.raises(InvalidInputError):
            create_document(storage, path, CONTENT)
    sdk.files_upload.assert_not_called()
    sdk.close.assert_called_once_with()


@pytest.mark.parametrize("selection", [None, "", "team1", "team6", "TEAM3", "team3 "])
def test_invalid_selection_fails_before_credential_loading(
    monkeypatch: pytest.MonkeyPatch, selection: str | None
) -> None:
    if selection is None:
        monkeypatch.delenv("STORAGE_IMPLEMENTATION", raising=False)
    else:
        monkeypatch.setenv("STORAGE_IMPLEMENTATION", selection)
    auth = Mock()
    monkeypatch.setattr(storage_composition, "get_dropbox_client", auth)

    with pytest.raises(ProviderFailureError) as caught:
        with contextmanager(get_document_storage)():
            pytest.fail("Invalid configuration supplied storage")

    assert caught.value.provider_involved is False
    auth.assert_not_called()


def test_credential_failure_is_sanitized_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_IMPLEMENTATION", "team3")
    auth = Mock(side_effect=DropboxAuthError("private credential details"))
    monkeypatch.setattr(storage_composition, "get_dropbox_client", auth)

    with pytest.raises(ProviderUnavailableError) as caught:
        with contextmanager(get_document_storage)():
            pytest.fail("Missing credentials supplied storage")

    assert str(caught.value) == "Storage credentials are unavailable"
    assert caught.value.retryable is True


def test_sdk_session_closes_when_workflow_fails(sdk: Mock) -> None:
    with pytest.raises(RuntimeError, match="later step failed"):
        with contextmanager(get_document_storage)():
            raise RuntimeError("later step failed")
    sdk.close.assert_called_once_with()


def test_api_can_inject_the_configured_shared_storage(sdk: Mock) -> None:
    application = create_app()
    sdk.files_upload.return_value = metadata()

    # Exercise the handoff without defining the other workstream's public route.
    @application.post("/_test/storage")
    def store_document(
        storage: DocumentStorage = Depends(get_document_storage),
    ) -> FileInfo:
        return create_document(storage, PATH, CONTENT)

    with TestClient(application) as client:
        response = client.post("/_test/storage")

    assert response.status_code == 200
    assert response.json() == {
        "id": "id:document123",
        "name": "hw3-notes.md",
        "path": PATH,
        "size": len(CONTENT),
        "modified_at": "2026-11-16T00:00:00Z",
        "etag": "0123456789",
        "type": None,
    }
    sdk.close.assert_called_once_with()


def test_real_package_can_be_constructed_without_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("STORAGE_IMPLEMENTATION", "team3")
    monkeypatch.setenv("DROPBOX_ACCESS_TOKEN", "controlled-test-token")
    monkeypatch.delenv("DROPBOX_REFRESH_TOKEN", raising=False)
    monkeypatch.setenv("DROPBOX_TOKEN_FILE", str(tmp_path / "absent.json"))

    def reject_network(*args: object, **kwargs: object) -> None:
        pytest.fail("Construction must not contact a provider")

    monkeypatch.setattr(requests.Session, "send", reject_network)
    with contextmanager(get_document_storage)() as storage:
        assert isinstance(storage, DocumentStorage)

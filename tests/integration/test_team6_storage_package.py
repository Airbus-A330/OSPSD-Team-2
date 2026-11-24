"""Installed Team 6 S3 adapter with only the external SDK transport controlled."""

from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import Mock

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError  # type: ignore[import-untyped]
from botocore.response import StreamingBody  # type: ignore[import-untyped]
from calendar_contract import Event
from cloud_storage_api import DocumentStorage
from fastapi.testclient import TestClient

from app import storage_composition, workflow_composition
from app.errors import InvalidInputError, ProviderUnavailableError
from app.main import create_app
from app.storage import StorageWriteUncertainError, create_document
from app.storage_composition import get_document_storage
from app.workflows import IssueResult

PATH = "/kickoff-team6.md"
CONTENT = "# Meeting notes: café\n".encode()
SETTINGS = {
    "STORAGE_IMPLEMENTATION": "team6",
    "STORAGE_BACKEND": "s3",
    "S3_ENDPOINT": "https://s3.example.invalid",
    "S3_REGION": "test-region",
    "S3_BUCKET": "test-bucket",
    "S3_ACCESS_KEY": "test-key",
    "S3_SECRET_KEY": "test-secret",
}


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("MAX_UPLOAD_BYTES", raising=False)
    monkeypatch.delenv("WORKFLOW_IMPLEMENTATION", raising=False)
    monkeypatch.delenv("WORKFLOW_FAIL_STEP", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")


@pytest.fixture
def sdk(configured: None, monkeypatch: pytest.MonkeyPatch) -> Mock:
    client = Mock()
    stored: dict[str, bytes] = {}

    def head(*, Bucket: str, Key: str) -> dict[str, object]:
        if Key not in stored:
            raise ClientError(
                {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )
        return {
            "ContentLength": len(stored[Key]),
            "ContentType": "text/markdown",
            "ETag": '"test-etag"',
            "LastModified": datetime(2026, 11, 23, tzinfo=UTC),
        }

    def upload(stream: BytesIO, bucket: str, key: str, **kwargs: object) -> None:
        stored[key] = stream.read()

    def download(*, Bucket: str, Key: str) -> dict[str, object]:
        return {
            **head(Bucket=Bucket, Key=Key),
            "Body": StreamingBody(BytesIO(stored[Key]), len(stored[Key])),
        }

    client.head_object.side_effect = head
    client.upload_fileobj.side_effect = upload
    client.get_object.side_effect = download
    monkeypatch.setattr(boto3, "client", Mock(return_value=client))
    monkeypatch.setattr(
        storage_composition,
        "get_dropbox_client",
        Mock(side_effect=AssertionError("Team 6 must not load Dropbox credentials")),
    )
    return client


def test_team6_create_read_and_conflict_use_shared_contract(sdk: Mock) -> None:
    with contextmanager(get_document_storage)() as storage:
        assert isinstance(storage, DocumentStorage)
        info = create_document(storage, PATH, CONTENT)
        assert info.id is None  # S3 has paths, not a Dropbox-style file ID.
        assert info.path == PATH and info.size == len(CONTENT)
        assert storage.get_metadata(PATH) == info
        assert storage.download(PATH) == CONTENT
        with pytest.raises(InvalidInputError, match="already exists"):
            create_document(storage, PATH, b"must not overwrite")
        assert storage.download(PATH) == CONTENT
    assert sdk.upload_fileobj.call_count == 1


@pytest.mark.parametrize("missing", list(SETTINGS.keys())[2:])
def test_missing_s3_settings_fail_before_sdk_construction(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    monkeypatch.setenv(missing, "  ")
    constructor = Mock(side_effect=AssertionError("Must fail before SDK construction"))
    monkeypatch.setattr(boto3, "client", constructor)
    with pytest.raises(ProviderUnavailableError) as caught:
        with contextmanager(get_document_storage)():
            pytest.fail("Missing credentials supplied storage")
    assert caught.value.provider_involved is False
    assert "test-secret" not in str(caught.value)
    constructor.assert_not_called()


@pytest.mark.parametrize("backend", ["", "memory", "unknown"])
def test_team6_never_falls_back_to_memory(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", backend)
    constructor = Mock()
    monkeypatch.setattr(storage_composition, "document_storage_from_env", constructor)
    with pytest.raises(ProviderUnavailableError):
        with contextmanager(get_document_storage)():
            pytest.fail("Non-S3 backend supplied real storage")
    constructor.assert_not_called()


def test_upstream_configuration_error_is_sanitized(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "private-invalid-value")
    with pytest.raises(ProviderUnavailableError) as caught:
        with contextmanager(get_document_storage)():
            pytest.fail("Invalid upstream configuration supplied storage")
    assert str(caught.value) == "Team 6 storage configuration is invalid"


def test_uncertain_team6_write_is_not_retried_by_our_adapter(sdk: Mock) -> None:
    sdk.upload_fileobj.side_effect = EndpointConnectionError(
        endpoint_url="https://private-provider.invalid"
    )
    with contextmanager(get_document_storage)() as storage:
        with pytest.raises(StorageWriteUncertainError) as caught:
            create_document(storage, PATH, CONTENT)
    assert caught.value.retryable is False
    assert "private-provider" not in str(caught.value)
    assert sdk.upload_fileobj.call_count == 1


@pytest.mark.parametrize("failed", [False, True])
def test_existing_http_workflow_uses_team6_and_preserves_partial_results(
    sdk: Mock,
    monkeypatch: pytest.MonkeyPatch,
    failed: bool,
) -> None:
    calendar = Mock()
    calendar.create.return_value = Event(
        id="event-test",
        title="Kickoff",
        start="2030-01-07T15:00:00Z",
        end="2030-01-07T15:30:00Z",
    )
    issues = Mock()
    issues.create_issue.return_value = IssueResult(id="issue-test", title="Kickoff")
    monkeypatch.setattr(
        workflow_composition,
        "open_calendar_service",
        lambda: nullcontext(calendar),
    )
    monkeypatch.setattr(
        workflow_composition,
        "open_issue_creator",
        lambda: nullcontext(issues),
    )
    if failed:
        sdk.upload_fileobj.side_effect = EndpointConnectionError(
            endpoint_url="https://private-provider.invalid"
        )
    with TestClient(create_app()) as client:
        response = client.post(
            "/workflows/project-kickoff",
            json={
                "event": {
                    "title": "Kickoff",
                    "start": "2030-01-07T15:00:00Z",
                    "end": "2030-01-07T15:30:00Z",
                },
                "document_path": PATH,
                "document_content": CONTENT.decode(),
                "issue_title": "Kickoff",
            },
        )
    body = response.json()
    if failed:
        assert response.status_code == 502
        assert body["failed_step"] == "storage"
        assert body["steps"]["calendar"]["event"]["id"] == "event-test"
        assert body["steps"]["storage"]["outcome"] == "uncertain"
        assert body["steps"]["issue_tracker"]["outcome"] == "not_attempted"
        assert body["error"]["retryable"] is False
        issues.create_issue.assert_not_called()
    else:
        assert response.status_code == 201
        assert body["storage"]["document"] == {"id": None, "path": PATH}
        assert body["issue_tracker"]["issue"]["id"] == "issue-test"
    assert "private-provider" not in response.text
    assert sdk.upload_fileobj.call_count == 1


def test_real_team6_construction_does_not_contact_provider(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from botocore.httpsession import URLLib3Session  # type: ignore[import-untyped]

    monkeypatch.setattr(
        URLLib3Session,
        "send",
        Mock(side_effect=AssertionError("Construction must not contact provider")),
    )
    with contextmanager(get_document_storage)() as storage:
        assert isinstance(storage, DocumentStorage)

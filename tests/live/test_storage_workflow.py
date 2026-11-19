"""Opt-in package-to-Dropbox verification; this does not verify deployment."""

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from cloud_storage_api import ConflictError, NotFoundError

from app.storage import create_document
from app.storage_composition import get_document_storage

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_STORAGE") != "1",
    reason="Opt-in live Dropbox verification writes disposable test-account data",
)


def test_live_document_create_read_conflict_delete() -> None:
    """Verify exact content and no overwrite; clean up confirmed creations only."""
    if os.getenv("STORAGE_IMPLEMENTATION") != "team3":
        pytest.fail("Set STORAGE_IMPLEMENTATION=team3", pytrace=False)
    path = "/ospsd-team2-verification-" + uuid4().hex + ".md"
    content = b"# HW3 Team 2 storage verification\nCalendar event: test-event\n"
    created = False
    with contextmanager(get_document_storage)() as storage:
        try:
            info = create_document(storage, path, content)
            created = True
            assert info.path == path
            assert info.size == len(content)
            assert storage.get_metadata(path) == info
            assert storage.download(path) == content
            with pytest.raises(ConflictError):
                storage.create(path, b"must not overwrite")
            assert storage.download(path) == content
        finally:
            # An uncertain create is left for reconciliation, never reported as
            # cleaned up. Retain the known path locally for that investigation.
            if created:
                storage.delete(path)
                with pytest.raises(NotFoundError):
                    storage.get_metadata(path)
            else:
                print("Unconfirmed verification path; inspect before retry:", path)

"""Configuration and request lifetime for the external storage implementation."""

import os
from collections.abc import Iterator

from cloud_storage_api import DocumentStorage
from dropbox_client_impl import (
    DropboxAuthError,
    DropboxClient,
    DropboxDocumentStorage,
    get_dropbox_client,
)

from app.errors import ProviderFailureError, ProviderUnavailableError


def get_document_storage() -> Iterator[DocumentStorage]:
    """Supply shared-contract storage as a FastAPI generator dependency.

    Selection is explicit; unsupported or missing selections fail before auth.
    Team 3 owns credential loading and provider behavior. Construction makes no
    provider call, and the SDK session closes after the request, even on failure.

    Raises:
        ProviderFailureError: If STORAGE_IMPLEMENTATION is not supported.
        ProviderUnavailableError: If credentials cannot be loaded before a write.
    """
    if os.environ.get("STORAGE_IMPLEMENTATION") != "team3":
        raise ProviderFailureError(
            "Set STORAGE_IMPLEMENTATION=team3", provider_involved=False
        )
    try:
        sdk = get_dropbox_client()
    except DropboxAuthError:
        raise ProviderUnavailableError(
            "Storage credentials are unavailable", provider_involved=True
        ) from None

    try:
        # Dropbox defaults include automatic 5xx and unbounded 429 retries.
        # Disable them at construction so an uncertain write is not repeated.
        client = sdk.clone(max_retries_on_error=0, max_retries_on_rate_limit=0)
        yield DropboxDocumentStorage(DropboxClient(dbx=client))
    finally:
        # clone() shares the original session; its owner closes it exactly once.
        sdk.close()

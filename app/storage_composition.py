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
from storage_service.config import ConfigError  # type: ignore[import-untyped]
from storage_service.wiring import document_storage_from_env  # type: ignore[import-untyped]

from app.errors import ProviderFailureError, ProviderUnavailableError


def get_document_storage() -> Iterator[DocumentStorage]:
    """Supply shared-contract storage as a FastAPI generator dependency.

    Selection is explicit; unsupported or missing selections fail before auth.
    Each team owns credential loading and provider behavior. Construction makes
    no provider call. Team 3's session is closed after the request; Team 6's
    public adapter exposes no close operation (see docs/STORAGE.md).

    Raises:
        ProviderFailureError: If STORAGE_IMPLEMENTATION is not supported.
        ProviderUnavailableError: If credentials cannot be loaded before a write.
    """
    selection = os.environ.get("STORAGE_IMPLEMENTATION")
    if selection == "team6":
        # A memory backend must never masquerade as the real-provider swap.
        required = (
            "S3_ENDPOINT",
            "S3_REGION",
            "S3_BUCKET",
            "S3_ACCESS_KEY",
            "S3_SECRET_KEY",
        )
        if os.environ.get("STORAGE_BACKEND") != "s3" or any(
            not os.environ.get(name, "").strip() for name in required
        ):
            raise ProviderUnavailableError(
                "Team 6 storage configuration is incomplete", provider_involved=False
            )
        try:
            storage = document_storage_from_env(os.environ)
        except ConfigError:
            raise ProviderUnavailableError(
                "Team 6 storage configuration is invalid", provider_involved=False
            ) from None
        yield storage
        return
    if selection != "team3":
        raise ProviderFailureError(
            "Set STORAGE_IMPLEMENTATION=team3 or team6", provider_involved=False
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

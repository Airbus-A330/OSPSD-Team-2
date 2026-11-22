"""Composition-facing document creation through the shared storage contract."""

from cloud_storage_api import (
    ConflictError,
    DocumentStorage,
    FileInfo,
    FileTooLargeError,
    InvalidOperationError,
    InvalidRequestError,
    NotFoundError as StorageNotFoundError,
    PermissionDeniedError as StoragePermissionDeniedError,
    StorageError,
)

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    StorageConflictError,
)


class StorageWriteUncertainError(ProviderFailureError):
    """A storage write failed without proof that the provider rejected it.

    Uses the existing non-retryable provider_error model. The workflow must
    retain earlier results and reconcile this path before attempting any retry.
    """


def create_document(storage: DocumentStorage, path: str, content: bytes) -> FileInfo:
    """Create once without overwriting, mapping storage failures to service errors.

    Args:
        storage: A configured implementation of the shared contract.
        path: Stable absolute document path retained by the workflow caller.
        content: Exact document bytes to store.

    Returns:
        Shared metadata confirming creation; never a raw provider response.

    Raises:
        InvalidInputError: Invalid content or path.
        StorageConflictError: The create-only destination already exists.
        NotFoundError: A required storage resource is missing.
        PermissionDeniedError: Storage refused access.
        StorageWriteUncertainError: Creation may have committed despite failure.
    """
    try:
        return storage.create(path, content)
    except ConflictError:
        raise StorageConflictError() from None
    except (InvalidRequestError, InvalidOperationError, FileTooLargeError):
        raise InvalidInputError(
            "Invalid storage document", public_message="Invalid storage document"
        ) from None
    except StorageNotFoundError:
        raise NotFoundError("Storage resource not found") from None
    except StoragePermissionDeniedError:
        raise PermissionDeniedError("Storage access denied") from None
    except StorageError:
        # The shared contract does not distinguish pre-write transport failures
        # from a lost response after commit, including ProviderUnavailableError.
        raise StorageWriteUncertainError("Storage write outcome is uncertain") from None

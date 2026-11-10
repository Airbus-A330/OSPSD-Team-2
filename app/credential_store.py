"""Non-interactive OAuth credentials cached locally for a single hosted worker."""

import os
import tempfile
from pathlib import Path
from threading import RLock

from google.auth.exceptions import RefreshError
from google.auth.transport import Request as AuthRequest
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.errors import ProviderFailureError

# The supported deployment has one worker. Threads must reload under this lock
# so concurrent requests do not refresh and overwrite the same token file.
_credential_lock = RLock()


def write_token_atomically(path: Path, contents: str) -> None:
    """Replace a token cache with a private file on the same filesystem."""
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            os.chmod(temporary, 0o600)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


class _CachedCredentials(Credentials):
    """Cache refreshes initiated either by us or by the Google HTTP client."""

    token_path: Path

    def refresh(self, request: AuthRequest) -> None:
        with _credential_lock:
            try:
                current = Credentials.from_authorized_user_file(
                    str(self.token_path), self.scopes
                )
                # Another request may have refreshed since this client loaded.
                # A still-valid *same* token must refresh on an SDK 401 callback.
                if not current.valid or current.token == self.token:
                    current.refresh(request)
                    write_token_atomically(self.token_path, current.to_json())
                self.token = current.token
                self.expiry = current.expiry
            except (OSError, ValueError, RefreshError):
                raise ProviderFailureError(
                    "Google authorization requires operator setup"
                ) from None


def load_hosted_credentials(path: Path, scopes: tuple[str, ...]) -> Credentials:
    """Load a request-local client that also caches later SDK refreshes.

    Transport failures propagate to the provider's existing error translator.
    Refresh rejection and local file failures become sanitized service errors.
    """
    with _credential_lock:
        try:
            credentials = _CachedCredentials.from_authorized_user_file(
                str(path), scopes
            )
            credentials.token_path = path
            if not credentials.refresh_token:
                raise ValueError("Missing refresh token")
            if not credentials.valid:
                credentials.refresh(Request())
            return credentials
        except (OSError, ValueError, RefreshError):
            raise ProviderFailureError(
                "Google authorization requires operator setup"
            ) from None

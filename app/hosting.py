"""Hosted entry point: validate configuration, protect traffic, report readiness.

Local development keeps using app.main:app. Containers use this module and
never attempt interactive Google authorization or probe Google for readiness.
"""

import json
import os
import secrets
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from google.oauth2.credentials import Credentials
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.credential_store import write_token_atomically
from app.google_calendar import GOOGLE_CALENDAR_SCOPES
from app.main import create_app


class StartupConfigurationError(RuntimeError):
    """A sanitized deployment configuration failure."""


def prepare_runtime() -> str:
    """Validate runtime inputs and seed persistent OAuth state only if absent.

    No network request is made. Actual authorization and provider availability
    are checked by the post-deploy smoke test, not the platform health probe.
    """
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "")
    api_token = os.environ.get("CALENDAR_API_TOKEN", "")
    token_file = os.environ.get("GOOGLE_CALENDAR_TOKEN_FILE", "")
    if not calendar_id.strip():
        raise StartupConfigurationError("GOOGLE_CALENDAR_ID is required")
    if (
        len(api_token) < 32
        or not api_token.isascii()
        or any(c.isspace() for c in api_token)
    ):
        raise StartupConfigurationError(
            "CALENDAR_API_TOKEN must be at least 32 ASCII characters without whitespace"
        )
    if not token_file or not Path(token_file).is_absolute():
        raise StartupConfigurationError(
            "GOOGLE_CALENDAR_TOKEN_FILE must be an absolute writable path"
        )
    path = Path(token_file)
    try:
        raw = (
            path.read_text(encoding="utf-8")
            if path.exists()
            else os.environ.get("GOOGLE_CALENDAR_TOKEN_JSON", "")
        )
        info = json.loads(raw)
        if not isinstance(info, dict) or any(
            not isinstance(info.get(key), str) or not info[key].strip()
            for key in ("client_id", "client_secret", "refresh_token")
        ):
            raise ValueError("Incomplete authorization")
        credentials = Credentials.from_authorized_user_info(
            info, GOOGLE_CALENDAR_SCOPES
        )
        # Validate parsing even if authorization is expired; refreshing at startup
        # would turn a transient Google outage into a restart loop.
        if not credentials.refresh_token:
            raise ValueError("Missing refresh token")
        if not path.parent.is_dir():
            raise ValueError("Persistent directory must be mounted first")
        if not path.exists():
            write_token_atomically(path, raw)
        else:
            os.chmod(path, 0o600)
            # Check actual write access without changing the saved authorization.
            with path.open("a", encoding="utf-8"):
                pass
        # Atomic refresh also needs a writable parent directory.
        with tempfile.TemporaryFile(dir=path.parent):
            pass
    except (OSError, ValueError, TypeError):
        raise StartupConfigurationError(
            "OAuth setup invalid: provide authorized-user JSON and a writable persistent token directory"
        ) from None
    os.environ["GOOGLE_CALENDAR_NONINTERACTIVE"] = "1"
    return api_token


class HostedAccess:
    """Require a runtime bearer token except for process-health probes."""

    def __init__(self, app: ASGIApp, *, application: FastAPI) -> None:
        self.app = app
        self.application = application

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not (
            scope["path"] in ("/healthz", "/readyz")
            and scope["method"] in ("GET", "HEAD")
        ):
            expected = getattr(self.application.state, "api_token", "")
            supplied = dict(scope["headers"]).get(b"authorization", b"")
            if not expected or not secrets.compare_digest(
                supplied, f"Bearer {expected}".encode("ascii")
            ):
                response = JSONResponse(
                    {
                        "error": {
                            "code": "access_denied",
                            "message": "Deployment access denied",
                            "retryable": False,
                        }
                    },
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_hosted_app() -> FastAPI:
    """Wrap the existing API with deployment-only lifecycle and access checks."""
    application = create_app()
    application.state.ready = False

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.api_token = prepare_runtime()
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            app.state.api_token = ""

    application.router.lifespan_context = lifespan
    application.add_middleware(HostedAccess, application=application)

    @application.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "alive"}

    @application.get("/readyz", include_in_schema=False)
    async def ready() -> JSONResponse:
        is_ready = application.state.ready
        return JSONResponse(
            {"status": "ready" if is_ready else "not_ready"},
            status_code=200 if is_ready else 503,
        )

    return application


app = create_hosted_app()

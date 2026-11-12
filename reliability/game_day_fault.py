"""Opt-in fault-image entry point; never included in the normal service image."""

from time import monotonic

from fastapi import FastAPI
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.hosting import create_hosted_app

# Synthetic missing-event identifier, not an identifier copied from user data.
FAULT_EVENT_ID = "d3c0beef12344b768aab0c0d0e0f1234"
FAULT_PATH = "/events/" + FAULT_EVENT_ID
MAX_FAULT_SECONDS = 300


class BoundedGetFault:
    """Reject one authenticated synthetic Get for at most five minutes/process."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.started_at: float | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] == "GET"
            and scope["path"] == FAULT_PATH
        ):
            now = monotonic()
            if self.started_at is None:
                self.started_at = now
            if now - self.started_at < MAX_FAULT_SECONDS:
                response = JSONResponse(
                    {
                        "error": {
                            "code": "provider_unavailable",
                            "message": "Controlled game-day failure",
                            "retryable": True,
                        }
                    },
                    status_code=503,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_faulty_app() -> FastAPI:
    """Keep normal lifecycle, outer telemetry and authentication around the fault."""
    application = create_hosted_app()
    application.user_middleware.append(Middleware(BoundedGetFault))
    return application


app = create_faulty_app()

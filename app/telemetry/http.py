"""ASGI instrumentation with fixed operations and no body/header capture."""

import re
from contextlib import ExitStack
from time import perf_counter
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.telemetry.runtime import CURRENT, isolated


def operation_for(method: str, path: str) -> str | None:
    """Map only the shared route shapes, never retaining an event identifier."""
    if method == "POST" and path == "/events":
        return "Create"
    if re.fullmatch(r"/events/[^/]+", path):
        return {"GET": "Get", "PUT": "Replace", "DELETE": "Delete"}.get(method)
    return None


def outcome_for(status: int, operation: str | None = None) -> str:
    """Use shared error categories plus explicit HTTP/application fallbacks."""
    if status < 400:
        expected = {"Create": 201, "Get": 200, "Replace": 200, "Delete": 204}
        if operation in expected and status != expected[operation]:
            return "unexpected_status"
        return "success"
    return {
        400: "invalid_input",
        422: "invalid_input",
        403: "access_denied",
        404: "not_found",
        502: "provider_error",
        503: "provider_unavailable",
    }.get(status, "application_error" if status >= 500 else "client_error")


class CalendarTelemetryMiddleware:
    """Wrap requests without consuming bodies or altering application failures."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        operation = (
            operation_for(scope["method"], scope["path"])
            if scope["type"] == "http"
            else None
        )
        application = scope.get("app")
        telemetry = (
            getattr(application.state, "telemetry", None) if application else None
        )
        if operation is None or telemetry is None:
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        request_id = uuid4().hex
        status = 500
        span = None
        stack = ExitStack()
        token = CURRENT.set(telemetry)
        with isolated():
            # Only W3C traceparent is accepted; baggage and other headers are omitted.
            carrier = {
                "traceparent": value.decode("ascii", errors="replace")
                for key, value in scope.get("headers", [])
                if key == b"traceparent" and len(value) <= 128
            }
            span = telemetry.tracer.start_span(
                "calendar." + operation,
                context=TraceContextTextMapPropagator().extract(carrier),
                kind=trace.SpanKind.SERVER,
                attributes={
                    "operation": operation,
                    "release": telemetry.release,
                    "request_id": request_id,
                },
            )
            stack.enter_context(
                trace.use_span(
                    span, record_exception=False, set_status_on_exception=False
                )
            )

        async def observe_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                with isolated():
                    message = dict(message)
                    message["headers"] = list(message.get("headers", [])) + [
                        (b"x-request-id", request_id.encode("ascii"))
                    ]
            await send(message)

        try:
            await self.app(scope, receive, observe_send)
        finally:
            with isolated():
                telemetry.record_request(
                    operation,
                    status,
                    outcome_for(status, operation),
                    perf_counter() - started,
                    request_id,
                )
            with isolated():
                if span is not None:
                    span.set_attribute("http.response.status_code", status)
                    outcome = outcome_for(status, operation)
                    span.set_attribute("outcome", outcome)
                    if status >= 500 or outcome == "unexpected_status":
                        span.set_status(trace.StatusCode.ERROR)
            with isolated():
                stack.close()
            with isolated():
                if span is not None:
                    span.end()
            CURRENT.reset(token)

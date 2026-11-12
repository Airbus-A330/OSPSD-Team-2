"""FastAPI application entry point for the Calendar service."""

from calendar_contract import CalendarError
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.routes import router
from app.telemetry.http import CalendarTelemetryMiddleware
from app.telemetry.runtime import telemetry_lifespan
from app.composition import get_event_provider
from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ProviderUnavailableError,
)
from app.http_errors import (
    http_error_response,
    request_validation_error_response,
    service_error_response,
)


def create_app() -> FastAPI:
    """Create the HTTP application and register routes and error handlers."""
    application = FastAPI(lifespan=telemetry_lifespan)
    application.add_middleware(CalendarTelemetryMiddleware)
    application.add_exception_handler(HTTPException, http_error_response)
    application.add_exception_handler(
        RequestValidationError, request_validation_error_response
    )
    application.add_exception_handler(CalendarError, service_error_response)
    for error_type in (
        InvalidInputError,
        NotFoundError,
        PermissionDeniedError,
        ProviderFailureError,
        ProviderUnavailableError,
    ):
        application.add_exception_handler(error_type, service_error_response)
    application.include_router(router)
    return application


app = create_app()

__all__ = ["app", "create_app", "get_event_provider"]

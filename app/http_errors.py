"""Render expected service failures and log only safe operation context."""

import logging

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)

logger = logging.getLogger(__name__)

_ERROR_RESPONSES: dict[type[ServiceError], tuple[int, str, str]] = {
    InvalidInputError: (400, "invalid_input", "Invalid event ID"),
    NotFoundError: (404, "not_found", "Event not found"),
    PermissionDeniedError: (403, "permission_denied", "Permission denied"),
    ProviderFailureError: (502, "provider_error", "Calendar provider request failed"),
}


def service_error_response(request: Request, error: Exception) -> JSONResponse:
    """Render a supported service error using the fixed public contract.

    Exception text and request contents are deliberately excluded. Provider
    involvement describes whether provider setup or retrieval was attempted,
    not whether a remote request completed. Unexpected errors are not mapped.
    """
    for error_type, (status, code, message) in _ERROR_RESPONSES.items():
        if isinstance(error, error_type):
            break
    else:
        raise error

    operation = getattr(request.state, "operation", "get_event")
    if isinstance(error, InvalidInputError) and operation == "list_events":
        message = "Invalid event limit"
    elif isinstance(error, InvalidInputError) and operation == "create_event":
        message = "Invalid event data"
    elif isinstance(error, InvalidInputError) and operation not in {
        "get_event",
        "replace_event",
    }:
        message = "Invalid input"
    provider_involved = getattr(request.state, "provider_involved", None)
    if isinstance(error, InvalidInputError):
        message = getattr(request.state, "invalid_input_message", message)
    logger.warning(
        "Calendar operation failed: operation=%s code=%s status=%s "
        "provider_involved=%s",
        operation,
        code,
        status,
        provider_involved,
        extra={
            "operation": operation,
            "error_code": code,
            "provider_involved": provider_involved,
            "http_status": status,
        },
    )
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}
    )


def request_validation_error_response(
    request: Request, error: Exception
) -> JSONResponse:
    """Render malformed requests through the shared invalid-input contract."""
    if not isinstance(error, RequestValidationError):
        raise error
    return _invalid_request_response(request)


async def http_error_response(request: Request, error: Exception) -> Response:
    """Normalize body decoding errors while preserving other framework errors."""
    if not isinstance(error, HTTPException):
        raise error
    if error.status_code == 400 and isinstance(error.__cause__, UnicodeDecodeError):
        return _invalid_request_response(request)
    return await http_exception_handler(request, error)


def _invalid_request_response(request: Request) -> JSONResponse:
    route = request.scope.get("route")
    request.state.operation = getattr(route, "name", "request_validation")
    request.state.provider_involved = False
    if request.state.operation == "replace_event":
        request.state.invalid_input_message = "Invalid event replacement"
    return service_error_response(
        request, InvalidInputError("Request schema validation failed")
    )

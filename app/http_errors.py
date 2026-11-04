"""Render expected service failures and log only safe operation context."""

import logging

from calendar_contract import CalendarError, ErrorCode
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
    ProviderUnavailableError,
    ServiceError,
)

logger = logging.getLogger(__name__)

_ERROR_RESPONSES: dict[type[ServiceError], tuple[int, str, str]] = {
    InvalidInputError: (400, "invalid_input", "Invalid event ID"),
    NotFoundError: (404, "not_found", "Event not found"),
    PermissionDeniedError: (403, "permission_denied", "Permission denied"),
    ProviderFailureError: (502, "provider_error", "Calendar provider request failed"),
    ProviderUnavailableError: (
        503,
        "provider_unavailable",
        "Calendar provider is unavailable",
    ),
}

_SHARED_ERROR_RESPONSES: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.INVALID_INPUT: (422, "Invalid event ID"),
    ErrorCode.NOT_FOUND: (404, "Event not found"),
    ErrorCode.ACCESS_DENIED: (403, "Access denied"),
    ErrorCode.PROVIDER_ERROR: (502, "Calendar provider request failed"),
    ErrorCode.PROVIDER_UNAVAILABLE: (503, "Calendar provider is unavailable"),
}

_INVALID_MESSAGES = {
    "create_event": "Invalid event data",
    "delete_event": "Invalid event ID",
    "get_event": "Invalid event ID",
    "list_events": "Invalid event limit",
    "patch_event": "Invalid input",
    "replace_event": "Invalid event replacement",
}


def _operation_name(request: Request) -> str:
    """Return the matched route name without mutating request-local state."""
    route = request.scope.get("route")
    name = getattr(route, "name", None)
    return name if isinstance(name, str) else "request_validation"


def service_error_response(request: Request, error: Exception) -> JSONResponse:
    """Render a supported service error using the fixed public contract.

    Exception text and request contents are deliberately excluded. Provider
    involvement describes whether provider setup or retrieval was attempted,
    not whether a remote request completed. Unexpected errors are not mapped.
    """
    operation = _operation_name(request)
    shared_get = False
    retryable = False
    if operation == "get_event" and isinstance(error, CalendarError):
        shared_get = True
        status, message = _SHARED_ERROR_RESPONSES[error.code]
        code = error.code.value
        retryable = error.retryable
    else:
        for error_type, (status, code, message) in _ERROR_RESPONSES.items():
            if isinstance(error, error_type):
                break
        else:
            raise error
    if isinstance(error, InvalidInputError):
        message = error.public_message or _INVALID_MESSAGES.get(operation, message)
    provider_involved = getattr(error, "provider_involved", None)
    if provider_involved is None:
        provider_involved = True
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
    body: dict[str, object] = {"code": code, "message": message}
    if shared_get:
        body["retryable"] = retryable
    return JSONResponse(status_code=status, content={"error": body})


def request_validation_error_response(
    request: Request, error: Exception
) -> JSONResponse:
    """Render malformed requests through the shared invalid-input contract."""
    if not isinstance(error, RequestValidationError):
        raise error
    malformed_json = any(item.get("type") == "json_invalid" for item in error.errors())
    return _invalid_request_response(request, malformed_json=malformed_json)


async def http_error_response(request: Request, error: Exception) -> Response:
    """Normalize body decoding errors while preserving other framework errors."""
    if not isinstance(error, HTTPException):
        raise error
    if error.status_code == 400 and isinstance(error.__cause__, UnicodeDecodeError):
        return _invalid_request_response(request)
    return await http_exception_handler(request, error)


def _invalid_request_response(
    request: Request, *, malformed_json: bool = True
) -> JSONResponse:
    response = service_error_response(
        request,
        InvalidInputError(
            "Request schema validation failed",
            public_message=_INVALID_MESSAGES.get(_operation_name(request)),
            provider_involved=False,
        ),
    )
    if _operation_name(request) == "get_event" and malformed_json:
        response.status_code = 400
    return response

"""Render expected service failures and log only safe operation context."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

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
    provider_involved = getattr(request.state, "provider_involved", None)
    logger.warning(
        "Event retrieval failed: code=%s status=%s provider_involved=%s",
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

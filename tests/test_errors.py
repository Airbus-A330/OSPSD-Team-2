"""Construction and catching of provider-independent service failures."""

import pytest
from calendar_contract import CalendarError, ErrorCode

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ProviderUnavailableError,
    ServiceError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        InvalidInputError,
        NotFoundError,
        PermissionDeniedError,
        ProviderFailureError,
        ProviderUnavailableError,
    ],
)
def test_service_errors_preserve_exception_message(
    error_type: type[ServiceError],
) -> None:
    error = error_type("Internal diagnostic context")

    with pytest.raises(ServiceError) as exc_info:
        raise error

    assert exc_info.value is error
    assert str(error) == "Internal diagnostic context"
    assert error.args == ("Internal diagnostic context",)
    assert isinstance(error, CalendarError)


def test_service_error_names_carry_shared_codes_and_retryability() -> None:
    assert InvalidInputError("invalid").code is ErrorCode.INVALID_INPUT
    assert PermissionDeniedError().code is ErrorCode.ACCESS_DENIED
    unavailable = ProviderUnavailableError()
    assert unavailable.code is ErrorCode.PROVIDER_UNAVAILABLE
    assert unavailable.retryable is True

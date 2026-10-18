"""Construction and catching of provider-independent service failures."""

import pytest

from app.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    ProviderFailureError,
    ServiceError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        ServiceError,
        InvalidInputError,
        NotFoundError,
        PermissionDeniedError,
        ProviderFailureError,
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

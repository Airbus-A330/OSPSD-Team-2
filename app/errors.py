"""Service failure names backed by the shared Calendar error contract."""

from calendar_contract import CalendarError, ErrorCode


class ServiceError(CalendarError):
    """Base class for expected service failures."""

    def __init__(
        self,
        message: str = "",
        *,
        code: ErrorCode = ErrorCode.PROVIDER_ERROR,
        retryable: bool = False,
        provider_involved: bool | None = None,
    ) -> None:
        super().__init__(code=code, message=message, retryable=retryable)
        self.provider_involved = provider_involved


class InvalidInputError(ServiceError):
    """A request contains invalid provider-independent input."""

    def __init__(
        self,
        message: str,
        *,
        public_message: str | None = None,
        provider_involved: bool | None = None,
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.INVALID_INPUT,
            retryable=False,
            provider_involved=provider_involved,
        )
        self.public_message = public_message


class NotFoundError(ServiceError):
    """The requested event does not exist."""

    def __init__(
        self, message: str = "", *, provider_involved: bool | None = None
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.NOT_FOUND,
            retryable=False,
            provider_involved=provider_involved,
        )


class PermissionDeniedError(ServiceError):
    """Access to the requested event is denied."""

    def __init__(
        self, message: str = "", *, provider_involved: bool | None = None
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.ACCESS_DENIED,
            retryable=False,
            provider_involved=provider_involved,
        )


class ProviderFailureError(ServiceError):
    """A provider failure prevents a calendar operation from completing."""

    def __init__(
        self, message: str = "", *, provider_involved: bool | None = None
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PROVIDER_ERROR,
            retryable=False,
            provider_involved=provider_involved,
        )


class ProviderUnavailableError(ServiceError):
    """A temporary provider failure prevents a safe read from completing."""

    def __init__(
        self, message: str = "", *, provider_involved: bool | None = None
    ) -> None:
        super().__init__(
            message,
            code=ErrorCode.PROVIDER_UNAVAILABLE,
            retryable=True,
            provider_involved=provider_involved,
        )

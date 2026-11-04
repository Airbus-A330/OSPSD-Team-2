"""Provider-independent failures; exception messages are internal context only."""


class ServiceError(Exception):
    """Base class for expected service failures."""

    def __init__(
        self, message: str = "", *, provider_involved: bool | None = None
    ) -> None:
        super().__init__(message)
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
        super().__init__(message, provider_involved=provider_involved)
        self.public_message = public_message


class NotFoundError(ServiceError):
    """The requested event does not exist."""


class PermissionDeniedError(ServiceError):
    """Access to the requested event is denied."""


class ProviderFailureError(ServiceError):
    """A provider failure prevents a calendar operation from completing."""

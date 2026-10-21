"""Provider-independent failures; exception messages are internal context only."""


class ServiceError(Exception):
    """Base class for expected service failures."""


class InvalidInputError(ServiceError):
    """A request contains invalid provider-independent input."""


class NotFoundError(ServiceError):
    """The requested event does not exist."""


class PermissionDeniedError(ServiceError):
    """Access to the requested event is denied."""


class ProviderFailureError(ServiceError):
    """A provider failure prevents a calendar operation from completing."""

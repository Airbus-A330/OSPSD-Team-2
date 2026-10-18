"""Provider-independent failures; exception messages are internal context only."""


class ServiceError(Exception):
    """Base class for expected service failures."""


class InvalidInputError(ServiceError):
    """The event identifier is empty or contains only whitespace."""


class NotFoundError(ServiceError):
    """The requested event does not exist."""


class PermissionDeniedError(ServiceError):
    """Access to the requested event is denied."""


class ProviderFailureError(ServiceError):
    """A provider failure prevents event retrieval."""

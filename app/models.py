"""Public domain models for the Calendar Service."""

from pydantic import BaseModel


class Event(BaseModel):
    """Public event representation exposed by the service."""

    id: str
    title: str
    start: str
    end: str

"""Public domain models for the Calendar Service."""

from pydantic import BaseModel


class Event(BaseModel):
    id: str
    title: str
    start: str
    end: str

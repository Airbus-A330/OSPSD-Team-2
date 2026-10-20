"""Public domain models for the Calendar Service."""

import re
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class Event(BaseModel):
    """Public event representation exposed by the service."""

    id: str
    title: str
    start: str
    end: str


class EventReplacement(BaseModel):
    """Complete editable timed-event values, preserving supplied strings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    start: str
    end: str

    @model_validator(mode="after")
    def validate_replacement(self) -> Self:
        """Require a meaningful title and an increasing, offset-aware interval."""
        if not self.title.strip():
            raise ValueError("Title must contain meaningful content")
        times = []
        for value in (self.start, self.end):
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
                r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)",
                value,
            ):
                raise ValueError("Times must be RFC3339 strings with an offset")
            times.append(datetime.fromisoformat(value))
        if times[1] <= times[0]:
            raise ValueError("End must be after start")
        return self

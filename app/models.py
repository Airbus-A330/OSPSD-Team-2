"""Public domain models for the Calendar Service."""

from typing import Self

from calendar_contract import CreateEvent as CreateEventRequest
from calendar_contract import Event
from calendar_contract import ReplaceEvent as EventReplacement
from pydantic import BaseModel, ConfigDict, model_validator

__all__ = ["CreateEventRequest", "Event", "EventPatch", "EventReplacement"]


class EventPatch(BaseModel):
    """Explicit editable changes; omitted fields are never sent as changes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = None
    start: str | None = None
    end: str | None = None

    @model_validator(mode="after")
    def validate_supplied_fields(self) -> Self:
        """Require changes and reject explicit nulls rather than clearing values."""
        if not self.model_fields_set:
            raise ValueError("At least one editable field is required")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Supplied fields must be strings")
        return self

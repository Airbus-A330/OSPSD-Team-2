"""Application entry point for the Calendar Service."""

from fastapi import FastAPI

from app.events import get_event
from app.models import Event

app = FastAPI()


@app.get("/events/{event_id}", response_model=Event)
def read_event(event_id: str) -> Event:
    """Return an event from the configured calendar.

    Args:
        event_id: Identifier supplied in the request path.

    Returns:
        The event in the service's public representation.
    """
    return get_event(event_id)


def main() -> None:
    """Run the application entry point."""


if __name__ == "__main__":
    main()

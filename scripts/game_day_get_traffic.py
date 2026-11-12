"""Generate bounded Get traffic against an explicitly disposable deployment."""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import httpx


@dataclass(frozen=True)
class Settings:
    """Validated operator inputs for the temporary game-day traffic run."""

    base_url: str
    event_id: str
    api_token: str
    request_count: int
    interval_seconds: float


def load_settings() -> Settings:
    """Load inputs and refuse any target not explicitly marked disposable."""
    base_url = os.getenv("CALENDAR_BASE_URL", "").rstrip("/")
    event_id = os.getenv("CALENDAR_GAME_DAY_EVENT_ID", "")
    api_token = os.getenv("CALENDAR_API_TOKEN", "")
    expected_host = os.getenv("CALENDAR_GAME_DAY_EXPECTED_HOST", "")
    confirmation = os.getenv("CALENDAR_GAME_DAY_CONFIRM_DISPOSABLE", "")
    if not all((base_url, event_id, api_token, expected_host)):
        raise SystemExit("Missing required game-day environment configuration")
    if confirmation != "YES":
        raise SystemExit("Refusing traffic without explicit disposable confirmation")

    target = urlsplit(base_url)
    if (
        target.scheme != "https"
        or target.hostname != expected_host
        or target.username is not None
        or target.password is not None
        or target.query
        or target.fragment
        or target.path not in ("", "/")
    ):
        raise SystemExit("Refusing traffic because the target host is not authorized")

    try:
        request_count = int(os.getenv("CALENDAR_GAME_DAY_REQUEST_COUNT", "8"))
        interval_seconds = float(os.getenv("CALENDAR_GAME_DAY_INTERVAL_SECONDS", "20"))
    except ValueError as error:
        raise SystemExit("Invalid game-day traffic bounds") from error
    if not 8 <= request_count <= 50 or not 0 <= interval_seconds <= 30:
        raise SystemExit("Game-day traffic bounds are outside the safe range")
    if (request_count - 1) * interval_seconds > 300:
        raise SystemExit("Game-day traffic would exceed the five-minute fault window")

    return Settings(
        base_url=base_url,
        event_id=event_id,
        api_token=api_token,
        request_count=request_count,
        interval_seconds=interval_seconds,
    )


def classify(response: httpx.Response) -> str:
    """Return a bounded classification without exposing response contents."""
    try:
        body = response.json()
    except ValueError:
        return "success" if response.is_success else "unexpected_response"
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return str(error["code"])
    return "success" if response.is_success else "unexpected_response"


def main() -> int:
    """Issue bounded requests while printing only safe operational evidence."""
    settings = load_settings()
    path = "/events/" + quote(settings.event_id, safe="")
    headers = {"Authorization": f"Bearer {settings.api_token}"}
    with httpx.Client(
        base_url=settings.base_url,
        headers=headers,
        timeout=15,
        follow_redirects=False,
    ) as client:
        for attempt in range(settings.request_count):
            timestamp = datetime.now(timezone.utc).isoformat()
            try:
                response = client.get(path)
                print(
                    f"{timestamp} request={attempt + 1} "
                    f"status={response.status_code} classification={classify(response)}"
                )
            except httpx.RequestError:
                print(
                    f"{timestamp} request={attempt + 1} "
                    "status=unavailable classification=transport_error"
                )
            if attempt + 1 < settings.request_count:
                time.sleep(settings.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

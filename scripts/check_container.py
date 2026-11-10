"""Offline container smoke check; stdin to Docker, never uses real credentials."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn

from app.composition import get_calendar_service
from app.errors import ProviderUnavailableError
from app.hosting import create_hosted_app


def main() -> None:
    """Verify startup, health and access controls with networking disabled."""
    assert os.getuid() == 10001, "Runtime must use the unprivileged service user"
    assert not list(Path("/app").glob("*.json")), "Unexpected runtime JSON inputs"
    assert not Path("/app/.git").exists(), "Git history must not enter the image"
    assert not list(Path("/app/app").rglob("*.json")), "Unexpected JSON in app sources"
    failure = subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.hosting:app",
            "--host",
            "127.0.0.1",
            "--port",
            "18068",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert failure.returncode != 0, "Missing configuration must fail startup"
    assert "GOOGLE_CALENDAR_ID is required" in failure.stderr

    with tempfile.TemporaryDirectory(prefix="calendar-smoke-") as directory:
        os.environ.update(
            {
                "GOOGLE_CALENDAR_ID": "primary",
                "CALENDAR_API_TOKEN": "synthetic-test-key-" + "x" * 32,
                "GOOGLE_CALENDAR_TOKEN_FILE": str(Path(directory) / "token.json"),
                "GOOGLE_CALENDAR_TOKEN_JSON": json.dumps(
                    {
                        "client_id": "synthetic-client",
                        "client_secret": "synthetic-secret",
                        "refresh_token": "synthetic-refresh",
                        "token": "synthetic-access",
                        "expiry": "2000-01-01T00:00:00Z",
                    }
                ),
            }
        )
        application = create_hosted_app()

        class UnavailableService:
            def get(self, event_id: str) -> None:
                raise ProviderUnavailableError("Controlled provider outage")

        application.dependency_overrides[get_calendar_service] = lambda: (
            UnavailableService()
        )
        server = uvicorn.Server(
            uvicorn.Config(
                application,
                host="127.0.0.1",
                port=18068,
                log_level="error",
                access_log=False,
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while (
                not server.started and thread.is_alive() and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            assert server.started, "Server failed to start"

            def request(path: str, *, authorized: bool = False) -> tuple[int, dict]:
                headers = (
                    {"Authorization": "Bearer " + os.environ["CALENDAR_API_TOKEN"]}
                    if authorized
                    else {}
                )
                req = urllib.request.Request(
                    "http://127.0.0.1:18068" + path, headers=headers
                )
                try:
                    response = urllib.request.urlopen(req, timeout=3)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    return response.status, json.load(response)

            assert request("/readyz") == (200, {"status": "ready"})
            assert request("/events/test-event")[0] == 403
            assert request("/openapi.json", authorized=True)[0] == 200
            status, body = request("/events/test-event", authorized=True)
            assert status == 503 and body["error"]["retryable"] is True
            assert request("/readyz")[0] == 200
            assert request("/healthz")[0] == 200
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "Server failed to stop"
    print(
        "PASS: non-root image, configuration failure, runtime token, protected API, provider-independent readiness"
    )


if __name__ == "__main__":
    main()

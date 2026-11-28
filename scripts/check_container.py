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
from app.hosting import app as application
from app.hosting import prepare_runtime


def main() -> None:
    """Verify startup, health and access controls with networking disabled."""
    getuid = getattr(os, "getuid", None)
    assert callable(getuid), "Container check requires a POSIX runtime"
    assert getuid() == 10001, "Runtime must use the unprivileged service user"
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

        # No volume is mounted. Exercise the image's actual writable cache path,
        # including a fresh start after its local token file disappears.
        cache = Path("/var/data/token.json")
        os.environ["GOOGLE_CALENDAR_TOKEN_FILE"] = str(cache)
        for _ in range(2):
            prepare_runtime()
            assert cache.stat().st_mode & 0o777 == 0o600
            assert json.loads(cache.read_text())["refresh_token"] == "synthetic-refresh"
            cache.unlink()

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
            token_path = Path(os.environ["GOOGLE_CALENDAR_TOKEN_FILE"])
            assert token_path.stat().st_mode & 0o777 == 0o600, (
                "Runtime token must be readable/writable only by its owner"
            )

            def request(
                path: str, *, authorized: bool = False, data: bytes | None = None
            ) -> tuple[int, dict]:
                headers = (
                    {"Authorization": "Bearer " + os.environ["CALENDAR_API_TOKEN"]}
                    if authorized
                    else {}
                )
                req = urllib.request.Request(
                    "http://127.0.0.1:18068" + path,
                    data=data,
                    headers={**headers, "Content-Type": "application/json"},
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
            # Exercise packaged HW3 imports and the real HTTP composition route,
            # without networking or provider credentials. This is synthetic proof.
            os.environ["WORKFLOW_IMPLEMENTATION"] = "controlled"
            os.environ["WORKFLOW_FAIL_STEP"] = "storage"
            payload = json.dumps(
                {
                    "event": {
                        "title": "Container verification",
                        "start": "2030-01-07T15:00:00Z",
                        "end": "2030-01-07T15:30:00Z",
                    },
                    "document_path": "/container-verification.md",
                    "document_content": "synthetic",
                    "issue_title": "Container verification",
                }
            ).encode()
            assert request("/workflows/project-kickoff", data=payload)[0] == 403
            status, body = request(
                "/workflows/project-kickoff", authorized=True, data=payload
            )
            assert status == 403 and body["failed_step"] == "storage"
            assert body["failure_stage"] == "operation"
            assert body["steps"]["calendar"]["outcome"] == "not_attempted"
            assert body["steps"]["storage"]["outcome"] == "failed"
            assert body["steps"]["issue_tracker"]["outcome"] == "not_attempted"
            assert body["error"]["retryable"] is False
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "Server failed to stop"
    print(
        "PASS: non-root image, configuration failure, ephemeral token recovery, protected API, provider-independent readiness"
    )


if __name__ == "__main__":
    main()

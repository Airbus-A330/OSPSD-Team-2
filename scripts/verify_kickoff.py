"""Opt-in hosted workflow verification; never retry a potentially committed write."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from calendar_contract import ErrorCode

from app.workflows import ProjectKickoffFailureResult, ProjectKickoffResult
from scripts.smoke_calendar import require


def verify_kickoff(
    client: httpx.Client,
    report: dict[str, object],
    *,
    expected_failure: str | None = None,
) -> None:
    """Check one synthetic-input request, retaining only safe diagnostic metadata.

    Happy-path records are deliberately retained for direct provider inspection.
    The generated marker locates them even if a write response is lost. This
    check does not claim direct provider verification or automatic cleanup.
    """
    marker = "ospsd-kickoff-" + uuid4().hex
    report.update(
        marker=marker,
        mode="controlled_failure" if expected_failure else "configured_happy_path",
        outcome="failed",
        direct_provider_verification="pending",
        cleanup="not_started",
        stage="readiness",
    )
    response = client.get("/readyz")
    report["http_status"] = response.status_code
    require(response.status_code == 200, "Service is not ready")
    fields = {
        "title": marker,
        "start": "2030-01-07T15:00:00Z",
        "end": "2030-01-07T15:30:00Z",
    }
    document_path = "/" + marker + ".md"
    report["stage"] = "workflow_request"
    report.pop("http_status", None)
    report["cleanup"] = "reconciliation_required"
    response = client.post(
        "/workflows/project-kickoff",
        json={
            "event": fields,
            "document_path": document_path,
            "document_content": "# " + marker + "\n",
            "issue_title": marker,
        },
    )
    report["http_status"] = response.status_code
    if expected_failure:
        require(response.status_code == 403, "Expected controlled rejection")
        failure = ProjectKickoffFailureResult.model_validate(response.json())
        require(
            failure.failed_step == expected_failure
            and failure.failure_stage == "operation"
            and (
                failure.error.code.value
                if isinstance(failure.error.code, ErrorCode)
                else failure.error.code
            )
            == "access_denied"
            and failure.error.retryable is False,
            "Unexpected workflow failure",
        )
        steps = ("storage", "issue_tracker", "calendar")
        index = steps.index(expected_failure)
        outcomes = [getattr(failure.steps, name).outcome for name in steps]
        require(
            outcomes
            == ["succeeded"] * index + ["failed"] + ["not_attempted"] * (2 - index),
            "Unexpected partial progress",
        )
        report["failed_step"] = expected_failure
        report["step_outcomes"] = outcomes
        report["cleanup"] = "not_applicable_if_controlled_mode_confirmed"
        report["direct_provider_verification"] = "not_applicable_synthetic"
    else:
        require(response.status_code == 201, "Workflow did not succeed")
        result = ProjectKickoffResult.model_validate(response.json())
        event = result.calendar.event
        require(
            bool(event.id)
            and not event.id.startswith("controlled-")
            and event.title == marker
            and all(
                datetime.fromisoformat(getattr(event, key))
                == datetime.fromisoformat(fields[key])
                for key in ("start", "end")
            )
            and result.storage.document.path == document_path
            and bool(result.issue_tracker.issue.id)
            and not result.issue_tracker.issue.id.startswith("controlled-")
            and result.issue_tracker.issue.title == marker,
            "Combined values differ from the request",
        )
        report["step_outcomes"] = ["succeeded"] * 3
        report["cleanup"] = "retained_for_provider_inspection"
    report["outcome"] = "passed"


def main() -> None:
    """Read an API bearer token from the environment and save a sanitized report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-create", action="store_true", required=True)
    parser.add_argument(
        "--expected-failure", choices=["calendar", "storage", "issue_tracker"]
    )
    args = parser.parse_args()
    directory = Path(".runtime") / ("kickoff-" + uuid4().hex)
    directory.mkdir(parents=True, mode=0o700)
    evidence = directory / "verification.json"
    report: dict[str, object] = {
        "outcome": "failed",
        "stage": "configuration",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        url = os.environ["CALENDAR_BASE_URL"]
        parsed = urlsplit(url)
        require(
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment,
            "Expected an HTTPS origin",
        )
        token = os.environ["CALENDAR_API_TOKEN"]
        require(
            len(token) >= 32
            and token.isascii()
            and not any(c.isspace() for c in token),
            "Invalid API credential",
        )
        with httpx.Client(
            base_url=url,
            headers={"Authorization": "Bearer " + token},
            trust_env=False,
            timeout=90,
            follow_redirects=False,
        ) as client:
            verify_kickoff(client, report, expected_failure=args.expected_failure)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, RuntimeError):
        raise SystemExit(
            "Workflow verification failed; inspect the sanitized report. Do not retry before reconciliation."
        ) from None
    finally:
        evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Sanitized evidence:", evidence)


if __name__ == "__main__":
    main()

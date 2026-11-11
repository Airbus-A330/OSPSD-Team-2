"""Deploy one published digest to the existing Render service, then smoke-test."""

import argparse
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from scripts.render_blueprint import render_blueprint
from scripts.smoke_calendar import require, smoke_calendar


def _stage(report: dict[str, object], name: str) -> None:
    """Start a fixed diagnostic stage without carrying over an earlier status."""
    report["stage"] = name
    report.pop("http_status", None)


def _response_status(report: dict[str, object], response: httpx.Response) -> None:
    """Record only the numeric HTTP status, never headers or response content."""
    report["http_status"] = response.status_code


def _find_requested_deploy(
    client: httpx.Client,
    path: str,
    request_image: str,
    deadline: float,
    report: dict[str, object],
) -> str | None:
    """Search every list page for the unique digest-qualified request reference."""
    matches: set[str] = set()
    cursor = ""
    seen_cursors: set[str] = set()
    while True:
        require(time.monotonic() < deadline, "Queued deployment discovery timed out")
        params = {"limit": "100"}
        if cursor:
            params["cursor"] = cursor
        _stage(report, "deploy_discovery")
        response = client.get(path, params=params)
        _response_status(report, response)
        require(response.status_code == 200, "Render deployment discovery failed")
        rows = response.json()
        require(isinstance(rows, list), "Invalid Render deployment list")
        for row in rows:
            require(
                isinstance(row, dict) and isinstance(row.get("deploy"), dict),
                "Invalid Render deployment list entry",
            )
            deploy = row["deploy"]
            image = deploy.get("image")
            if isinstance(image, dict) and image.get("ref") == request_image:
                deploy_id = deploy["id"]
                require(
                    isinstance(deploy_id, str)
                    and bool(re.fullmatch(r"dep-[a-zA-Z0-9]+", deploy_id)),
                    "Invalid queued deployment ID",
                )
                matches.add(deploy_id)
        if len(rows) < 100:
            break
        cursor = rows[-1]["cursor"]
        require(
            isinstance(cursor, str) and bool(cursor) and cursor not in seen_cursors,
            "Invalid Render deployment pagination",
        )
        seen_cursors.add(cursor)
    if len(matches) > 1:
        report["candidate_deploy_ids"] = sorted(matches)
        raise RuntimeError("Ambiguous queued deployment identity")
    return next(iter(matches), None)


def deploy_image(
    client: httpx.Client, service_id: str, image: str, report: dict[str, object]
) -> None:
    """Submit once and track this request, including an empty queued response.

    The unique tag correlates list results; the digest still selects the exact
    published artifact. Never infer identity from recency or a shared digest.
    """
    repository, digest = image.rsplit("@", 1)
    request_image = f"{repository}:delivery-{uuid4().hex}@{digest}"
    report["request_image"] = request_image
    # Preserve the reference even if the POST acknowledgement is lost.
    report["reconciliation_required"] = True
    path = f"/v1/services/{service_id}/deploys"
    deadline = time.monotonic() + 900
    _stage(report, "deploy_request")
    response = client.post(path, json={"imageUrl": request_image})
    _response_status(report, response)
    if response.status_code in {400, 422}:
        # Some Render environments reject tag+digest references. Retry once with
        # the canonical digest reference before treating the request as failed.
        request_image = image
        report["request_image"] = request_image
        report["initial_deploy_http_status"] = response.status_code
        _stage(report, "deploy_request_fallback")
        response = client.post(path, json={"imageUrl": request_image})
        _response_status(report, response)
    require(response.status_code in (201, 202), "Render did not acknowledge deployment")
    report["platform"] = "accepted"
    payload: object = {}
    if response.content:
        try:
            payload = response.json()
        except ValueError:
            require(response.status_code == 202, "Invalid Render deployment response")
    deploy_id = payload.get("id") if isinstance(payload, dict) else None
    if deploy_id is None and response.status_code == 202:
        report["deployment_tracking"] = "awaiting_id"
        while deploy_id is None:
            deploy_id = _find_requested_deploy(
                client, path, request_image, deadline, report
            )
            if deploy_id is None:
                require(
                    time.monotonic() < deadline, "Queued deployment discovery timed out"
                )
                time.sleep(10)
    require(
        isinstance(deploy_id, str)
        and bool(re.fullmatch(r"dep-[a-zA-Z0-9]+", deploy_id)),
        "Invalid Render deployment ID",
    )
    report["deploy_id"] = deploy_id
    report["deployment_tracking"] = "identified"
    while True:
        _stage(report, "deploy_poll")
        response = client.get(f"{path}/{deploy_id}")
        _response_status(report, response)
        require(response.status_code == 200, "Render deployment lookup failed")
        status = response.json()["status"]
        if status == "live":
            report["platform"] = "live"
            return
        require(
            status
            in {
                "created",
                "queued",
                "build_in_progress",
                "update_in_progress",
                "pre_deploy_in_progress",
            },
            "Render deployment failed or entered an unsupported state",
        )
        require(time.monotonic() < deadline, "Render deployment timed out")
        time.sleep(10)


def main() -> None:
    """Retain sanitized success/failure evidence; secrets come only from runtime env."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--evidence", type=Path, default=Path("delivery.json"))
    args = parser.parse_args()
    report: dict[str, object] = {
        "image": args.image,
        "workflow_sha": os.getenv("GITHUB_SHA", "local"),
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "local"),
        "outcome": "failed",
        "smoke": "not_passed",
        "cleanup": "not_started",
    }
    try:
        _stage(report, "configuration")
        # Reuse the infrastructure owner's digest validation and template.
        blueprint = render_blueprint(args.image)
        args.evidence.with_suffix(".yaml").write_text(blueprint, encoding="utf-8")
        service_id = os.environ["RENDER_SERVICE_ID"]
        require(
            bool(re.fullmatch(r"srv-[a-zA-Z0-9]+", service_id)), "Invalid service ID"
        )
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
            "Expected an HTTPS service origin",
        )
        render_token = os.environ["RENDER_API_KEY"]
        calendar_token = os.environ["CALENDAR_API_TOKEN"]
        require(bool(render_token.strip()), "Missing Render credential")
        require(
            len(calendar_token) >= 32
            and calendar_token.isascii()
            and not any(character.isspace() for character in calendar_token),
            "Invalid Calendar access credential",
        )
        with httpx.Client(
            base_url="https://api.render.com",
            timeout=30,
            trust_env=False,
            headers={"Authorization": "Bearer " + render_token},
        ) as render:
            # Do not smoke a different healthy service and accidentally certify
            # a bad candidate. Require Render's canonical URL for this resource.
            _stage(report, "service_lookup")
            service = render.get(f"/v1/services/{service_id}")
            _response_status(report, service)
            require(service.status_code == 200, "Render service lookup failed")
            canonical_url = service.json()["serviceDetails"]["url"]
            require(
                isinstance(canonical_url, str)
                and canonical_url.rstrip("/") == url.rstrip("/"),
                "Smoke URL does not match the selected Render service",
            )
            deploy_image(render, service_id, args.image, report)
        _stage(report, "calendar_smoke")
        with httpx.Client(
            base_url=url,
            timeout=30,
            trust_env=False,
            headers={"Authorization": "Bearer " + calendar_token},
        ) as calendar:
            smoke_calendar(calendar, report)
        report["outcome"] = "successful"
        report["reconciliation_required"] = False
    except (httpx.HTTPError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        # HTTP exceptions and validation errors may contain URLs or provider
        # bodies. Retain only fixed metadata, never exception text or payloads.
        category = (
            "timeout"
            if isinstance(exc, httpx.TimeoutException)
            else "http_transport"
            if isinstance(exc, httpx.HTTPError)
            else "missing_field"
            if isinstance(exc, KeyError)
            else "invalid_data"
            if isinstance(exc, (ValueError, TypeError))
            else "validation_failed"
        )
        report["failure_stage"] = report["stage"]
        report["error_category"] = category
        raise SystemExit(
            f"Delivery failed: stage={report['stage']} "
            f"http_status={report.get('http_status', 'none')} category={category}; "
            "inspect sanitized evidence and operator runbook"
        ) from None
    finally:
        args.evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

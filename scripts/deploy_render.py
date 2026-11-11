"""Deploy one published digest to the existing Render service, then smoke-test."""

import argparse
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import httpx

from scripts.render_blueprint import render_blueprint
from scripts.smoke_calendar import require, smoke_calendar


def deploy_image(
    client: httpx.Client, service_id: str, image: str, report: dict[str, object]
) -> None:
    """Request the exact image once and wait for this deployment, never a prior one."""
    response = client.post(
        f"/v1/services/{service_id}/deploys", json={"imageUrl": image}
    )
    require(response.status_code == 201, "Render did not acknowledge deployment")
    deploy_id = response.json()["id"]
    require(
        isinstance(deploy_id, str)
        and bool(re.fullmatch(r"dep-[a-zA-Z0-9]+", deploy_id)),
        "Invalid Render deployment ID",
    )
    report["deploy_id"] = deploy_id
    deadline = time.monotonic() + 900
    while True:
        response = client.get(f"/v1/services/{service_id}/deploys/{deploy_id}")
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
            service = render.get(f"/v1/services/{service_id}")
            require(service.status_code == 200, "Render service lookup failed")
            canonical_url = service.json()["serviceDetails"]["url"]
            require(
                isinstance(canonical_url, str)
                and canonical_url.rstrip("/") == url.rstrip("/"),
                "Smoke URL does not match the selected Render service",
            )
            deploy_image(render, service_id, args.image, report)
        with httpx.Client(
            base_url=url,
            timeout=30,
            trust_env=False,
            headers={"Authorization": "Bearer " + calendar_token},
        ) as calendar:
            smoke_calendar(calendar, report)
        report["outcome"] = "successful"
    except (httpx.HTTPError, ValueError, KeyError, TypeError, RuntimeError):
        # HTTP exceptions and validation errors may contain URLs or provider
        # bodies. Retain only fixed metadata, never exception text or payloads.
        raise SystemExit(
            "Delivery failed; inspect sanitized evidence and operator runbook"
        ) from None
    finally:
        args.evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

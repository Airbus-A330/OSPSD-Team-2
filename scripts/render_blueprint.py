"""Render the IaC template using one immutable, already-published image."""

import argparse
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "infra" / "render.template.yaml"


def render_blueprint(image: str) -> str:
    """Reject mutable tags and credential-bearing URLs before producing IaC."""
    if not re.fullmatch(
        r"[a-z0-9][a-z0-9.-]*(?::[0-9]+)?/[a-z0-9._/-]+@sha256:[0-9a-f]{64}",
        image,
    ):
        raise ValueError("Expected registry/image@sha256:<64 lowercase hex digits>")
    if image.endswith("0" * 64):
        raise ValueError("Use a published image digest, not an all-zero placeholder")
    return TEMPLATE.read_text(encoding="utf-8").replace("__IMAGE_DIGEST_REF__", image)


def main() -> None:
    """Write reproducible IaC to stdout; applying infrastructure is separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        result = render_blueprint(args.image)
    except ValueError as error:
        parser.error(str(error))
    print(result, end="")


if __name__ == "__main__":
    main()

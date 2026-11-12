"""Check deterministic artifact selection for the Render IaC template."""

import pytest

from scripts.render_blueprint import render_blueprint


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/team/calendar:latest",
        "ghcr.io/team/calendar:commit123",
        "https://user:password@registry/image",
        "ghcr.io/team/calendar@sha256:short",
        "ghcr.io/team/calendar@sha256:" + "0" * 64,
        "ghcr.io/team/calendar@sha256:" + "a" * 64 + "\nservices: []",
    ],
)
def test_rejects_mutable_or_invalid_image_reference(image):
    with pytest.raises(ValueError):
        render_blueprint(image)


def test_same_digest_produces_identical_configuration():
    image = "ghcr.io/airbus-a330/ospsd-team-2@sha256:" + "a" * 64
    first = render_blueprint(image)
    assert first == render_blueprint(image)
    assert image in first
    assert "__IMAGE_DIGEST_REF__" not in first


def test_service_uses_free_compute_without_persistent_resources():
    rendered = render_blueprint("ghcr.io/team/calendar@sha256:" + "a" * 64)
    # Schema validation is separate; guard the cost/storage choice here.
    assert "    plan: free\n" in rendered
    assert "disk:" not in rendered
    assert "databases:" not in rendered
    assert "    healthCheckPath: /readyz\n" in rendered

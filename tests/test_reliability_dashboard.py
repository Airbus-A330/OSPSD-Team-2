"""Keep the importable live-measurement view aligned with canonical SLI rules."""

import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "ref_id,record",
    [
        ("A", "team2_calendar:get_eligible:increase7d"),
        ("B", "team2_calendar:get_good:increase7d"),
        ("C", "team2_calendar:get_latency_eligible:increase7d"),
        ("D", "team2_calendar:get_fast:increase7d"),
    ],
)
def test_live_measurement_panels_use_exact_canonical_instant_queries(
    ref_id: str, record: str
) -> None:
    dashboard = json.loads(
        (ROOT / "docs/reliability/measurement-dashboard.json").read_text()
    )
    records = dict(
        re.findall(
            r"- record: ([^\n]+)\n\s+expr: ([^\n]+)",
            (ROOT / "reliability/calendar.rules.yml").read_text(),
        )
    )
    assert dashboard["refresh"] == ""
    targets = [
        (panel["datasource"]["uid"], target)
        for panel in dashboard["panels"]
        for target in panel["targets"]
        if target["refId"] == ref_id
    ]
    assert dashboard["panels"][-1]["targets"] == [
        {
            "refId": "E",
            "instant": True,
            "range": False,
            "expr": 'time() - max(timestamp(calendar_requests_total{operation="Get"}))',
        }
    ]
    assert targets == [
        (
            "grafanacloud-prom",
            {"refId": ref_id, "instant": True, "range": False, "expr": records[record]},
        )
    ]

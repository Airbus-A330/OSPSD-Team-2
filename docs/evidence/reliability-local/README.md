# Local actual-telemetry integration — 2026-11-10

**Synthetic only. Not deployed Google verification, a 7-day observation period,
real Slack delivery, an independent recovery, or an extra-credit game day.**

## Provenance and execution

- Producer: isolated archive of PR #73, commit
  `3c7980a54b01bf302b5fff8177365559353fb3ca`; `uv sync --locked` with uv 0.12.17,
  Python 3.12.10. Its actual middleware, SDK instruments and OTLP exporter ran.
  Later rule/doc revalidation used Nicolas’s `822457f` exact-200 classification;
  metric names were unchanged, so this retained capture was not regenerated.
- Consumer: these #72 recording rules; checksum-verified native Prometheus
  **3.16.0**, OTLP receiver enabled, loopback-only, temporary storage. No Docker
  daemon, production service, cloud resources or Google credentials involved.
- Controlled HTTP route, **not** the shared provider implementation: 3 batches of
  statuses `200, 404, 400, 422, 403, 502, 503, 401`, followed by one slow 200
  (>1.05 seconds). Total **27** requests. First batch established initial samples;
  the next two changed cumulative counters. Metrics were force-flushed after
  each batch, not mocked into Prometheus.
- The real `make reliability-report PROMETHEUS_URL=<ephemeral-loopback>` command
  returned all 10 metrics. Assertions checked availability `3/7`, latency `6/7`,
  both negative remaining budgets, healthy rules and no event/body fields in
  the metric results. A closed-loopback report connection separately exited
  nonzero. Temporary Prometheus was terminated and its storage removed.

## Recorded values

Raw sanitized API results and fixture metadata: [`metrics.json`](metrics.json).
Report evaluation: **2026-11-10T02:59:42Z**, Unix `1794279582`.
Configured window: `(2026-11-03T02:59:42Z, 2026-11-10T02:59:42Z]`.
**Actual history was only this short local run, not seven days.**

| SLI | Numerator | Denominator | Value | Allowed bad | Remaining budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| Availability | 9 | 21 | 0.42857142857142855 | 0.21 | -11.79 |
| Latency | 18 | 21 | 0.8571428571428571 | 1.05 | -1.95 |

The synthetic error/slow cases deliberately overspend both budgets; these are
not estimates of production reliability. `increase` extrapolates samples: do not
generally equate it to literal request counts or infer complete history from it.

## Recheck retained calculations

From the repository root, without network or credentials:

```sh
python3 - <<'PY'
import json
import math
from pathlib import Path

result = json.loads(Path('docs/evidence/reliability-local/metrics.json').read_text())
values = {v['metric']['__name__']: float(v['value'][1])
          for v in result['report']['data']['result']}
assert len(values) == 10 and all(math.isfinite(v) for v in values.values())
assert result['provider_calls'] == 0 and not result['full_window_coverage_verified']
for objective, numerator, denominator, fraction in [
    ('availability', 'good', 'eligible', 0.01),
    ('latency', 'fast', 'latency_eligible', 0.05),
]:
    good = values[f'team2_calendar:get_{numerator}:increase7d']
    total = values[f'team2_calendar:get_{denominator}:increase7d']
    assert math.isclose(values[f'team2_calendar:get_{objective}:ratio7d'], good / total)
    assert math.isclose(values[f'team2_calendar:get_{objective}_allowed:budget7d'], total * fraction)
    assert math.isclose(values[f'team2_calendar:get_{objective}_remaining:budget7d'], total * fraction - (total - good))
print('Retained calculations: PASS (local synthetic only)')
PY
```

## Repeat the export integration

Use a **separate checkout** of the producer revision above and its locked dev
environment; do not merge teammate work just to run the fixture. Start a temporary
native Prometheus with these rules, `--web.enable-otlp-receiver`, temporary TSDB
storage, and `--web.listen-address=127.0.0.1:<unused-port>`.

Use PR #73's controlled-app pattern in `tests/telemetry/test_export.py`: attach
`CalendarTelemetryMiddleware`, supply `Telemetry` with a
`PeriodicExportingMetricReader` / HTTP `OTLPMetricExporter` aimed at
`http://127.0.0.1:<port>/api/v1/otlp/v1/metrics`, and return only synthetic status
responses from `/events/{event_id}`. Do not call the real provider. Run the batches
above with >=1 second between exports, flush metrics, and allow the one-minute
rule evaluation to run. Query using `make reliability-report`, verify the two
ratios/budgets and `/api/v1/rules` health, then stop the process and remove only
its temporary storage. Counter extrapolation can change absolute estimates.

This protocol checks the actual producer/consumer boundary, not body conformance,
hosted startup/lifespan, replica behavior, export-loss resistance, real alert
transport or real deployment recovery. Those still require the #72 live exercise.

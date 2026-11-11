# Get SLIs and SLOs

Owner: Maksym. **Definitions implemented; exact live SLI/budget capture pending.**

## Policy and measurement location

[Alexander's policy](https://github.com/Airbus-A330/OSPSD-Team-2/pull/74#issuecomment-6757433749)
and [inclusive bucket clarification](https://github.com/Airbus-A330/OSPSD-Team-2/pull/73#issuecomment-6757791352)
apply to `GET /events/{event_id}` (`operation="Get"`).

| Item | Definition |
| --- | --- |
| Eligible | Completed Get requests reaching service middleware; exclude only 400/422 (`invalid_input`) |
| Availability good | Exact 200 plus contract-correct 404 (`success` or `not_found`) |
| Availability bad | All other eligible responses, including 403/502/503 and unexpected 2xx/redirects |
| Latency good | Eligible requests completing in the upper-inclusive `le="1"` bucket: **<=1 second**, including 404 |
| Availability target/window | **99% over rolling 7 days** |
| Latency target/window | **95% over rolling 7 days** |
| Measurement location | Actual hosted HTTP middleware, entry through response completion; seconds |
| Rationale | Interactive-read consumer needs with a nonzero budget; not a claim of observed production performance |
| No traffic/missing data | Unknown/no-data, never automatically 100% healthy |

Fast provider failures still fail availability even if they pass latency. Retain
these agreed targets unless reviewed measurements justify a change.

## Capture the exact live values

Grafana: https://gianthamster2577.grafana.net/dashboards

Import [`measurement-dashboard.json`](measurement-dashboard.json) through
**Dashboards -> New -> Import -> Upload JSON**. It uses the actual Cloud datasource
UID `grafanacloud-prom` observed in the public dashboard. This creates a separate
measurement view, not a deployment or a replacement for Nick's dashboard.
The four count queries are instant queries; capture them at one UTC evaluation instant.
Also check the source-age panel: stale/no-data is not proof of current export.
Recent counts can remain in a 7-day lookback after the exporter stops.
Turn off refresh, verify no query errors and record the selected time. Use each
panel's **Inspect -> Data** export for unrounded values, not rounded stat text.
If the UI import is inconvenient, run these in Explore with that same datasource/time:

```promql
# A: availability denominator (eligible)
sum(increase(calendar_requests_total{operation="Get",outcome!="invalid_input"}[7d]))

# B: availability numerator (good)
sum(increase(calendar_requests_total{operation="Get",outcome=~"success|not_found"}[7d])) or vector(0)

# C: latency denominator
sum(increase(calendar_request_duration_seconds_count{operation="Get",outcome!="invalid_input"}[7d]))

# D: latency numerator (fast)
sum(increase(calendar_request_duration_seconds_bucket{operation="Get",outcome!="invalid_input",le="1"}[7d])) or vector(0)
```

Use only Team 2's tenant/environment. If the backend contains other environments,
apply its actual verified service/environment selector consistently to every
query before capturing; do not guess label names. Compare A and C. Empty results,
a zero denominator, query errors or unexplained denominator differences do not
establish a healthy result. Validate raw source names/labels in Explore first.

| Record at one evaluation instant | Current value |
| --- | --- |
| UTC evaluation time / backend scope / source releases | Pending exact live capture |
| Configured window | `(t - 604800 seconds, t]` |
| Actual observed history and gaps | Pending verification; do not claim full seven-day coverage |
| Availability numerator B / denominator A / SLI B/A | Pending exact live capture |
| Availability allowed / remaining bad-event budget | `A * 0.01` / `A * 0.01 - (A - B)`; pending values |
| Latency numerator D / denominator C / SLI D/C | Pending exact live capture |
| Latency allowed / remaining bad-event budget | `C * 0.05` / `C * 0.05 - (C - D)`; pending values |

For 1,000 eligible requests, the availability allowance is 10 bad events and
latency allowance is 50. Negative means overspent; zero means exhausted.
`increase` extrapolates, so counts/budgets may be fractional; retain unrounded
values. A single low-volume failure may exhaust a budget.

If the native recording rules are loaded, `make reliability-report
PROMETHEUS_URL=https://YOUR_APPROVED_PROMETHEUS_HOST` retrieves all ten recorded
values at one UTC instant. Supply authentication through protected curl
configuration, never URLs or Make arguments. A Grafana UI/OTLP ingestion URL is
not automatically the Prometheus query endpoint. The importable view above does
not require recording rules to have been loaded.

## Measurement limits and evidence

- Public traffic/error rates and p95 do **not** supply these exact SLI numerators
  and denominators. Do not integrate rounded rates or substitute p95 for <=1s.
- A 7-day lookback over a new backend is not seven days of observation. Investigate
  exporter gaps even if old samples exist; retain source data for the window.
- Counters cannot verify Event/error bodies. A broken 404 can look good; use
  shared conformance and the known-fixture smoke test independently.
- Server-side completed requests miss upstream/cold-start failures, never-ending
  requests and lost exports. Render Free sleeping adds delay before middleware;
  record cold-start smoke separately without discarding observed slow requests.
- Aggregate releases so deployments do not reset the budget. Distinct workers
  need separate cumulative stream identities; never merge colliding counters.
- Never label metrics with event IDs, URLs, request IDs or credentials.

[Live API/delivery evidence](../evidence/reliability-live/README.md) proves those
boundaries, not SLI completion. The new public dashboard check verifies that live
series exist; it does not replace the pending exact measurements above.
See [error-budget policy](error-budget-policy.md) for action on exhaustion.

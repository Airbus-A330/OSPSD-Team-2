# Local telemetry evidence — not deployed verification

Captured on 2026-11-10 UTC against the disposable Grafana LGTM 0.40.0 fixture,
release `local-restored-service-check`. No cloud deployment, live Google request,
Calendar credentials, teammate interpretation, or production failure injection
was performed. Requests exercised the **actual application factory, routes,
application/cache composition, shared GET adapter, and Google provider** restored
at `7116084`, with the telemetry work applied. Only the Google SDK boundary was
controlled. The real error translators produced 503 `provider_unavailable` for a
temporary GET failure and 502 `provider_error` for uncertain write failures.
The exact base revision, capture time, and verified source-file SHA-256 values
are recorded in `requests.json`; these are working-tree verification records.

This retained capture predates the shared-contract completion merged in PR #76.
It identifies its exact source rather than claiming to verify the newer base.
Current automated checks cover the full merged shared conformance suite; current
write validation uses 422 and shared error envelopes, unlike this historical
capture's HW1 write-validation responses. Deployed evidence remains outstanding.

Retained artifacts:

- [Dashboard screenshot](dashboard.png): latency, traffic, categorized errors,
  saturation, capacity, release identity, and correlated request logs.
- [Metrics/query exports](metrics.json): four operation series, shared error
  categories, histogram-derived latency, worker capacity 40, and peak utilization
  0.025 (one occupied worker of 40).
- [Request samples](requests.json): success, invalid-query, and synthetic provider
  failure for all four operation hooks. Four waves supplied nonzero rate data.
- [Three exported logs and traces](correlated-logs-and-traces.json): representative
  Get requests with success/200, invalid_input/422, and provider_unavailable/503. Trace
  IDs are hexadecimal in logs and protobuf base64 in Tempo's JSON response. The
  successful request deliberately held its controlled SDK call for 12 seconds,
  showing provider time separately from the surrounding application time.

Each representative log's trace ID was resolved through the actual Tempo data
source proxy. Success and provider failure have nested SERVER/CLIENT spans;
invalid input has only its SERVER span. The running local Grafana data source
configuration was inspected to confirm Loki's `trace_id` links target Tempo and
Tempo's trace-to-logs query uses the matching trace ID. The dashboard was rendered
in headless Chrome and visually inspected.

The retained three exported log records and trace payloads were manually
inspected by the implementing agent: resource attributes, span attributes,
statuses and events contained no tokens, authorization headers, Calendar
contents, raw URLs, request/response payloads, event IDs, or exception messages.
This is **local synthetic evidence**, not the required independent teammate or
deployed sensitivity review. Follow [the deployed verification procedure](../../OBSERVABILITY.md#required-deployed-verification-and-retained-evidence)
to complete the submission evidence.

Local validation performed:

```text
docker compose -p team2-telemetry-check -f observability/compose.yaml config --quiet
docker compose -p team2-telemetry-check -f observability/compose.yaml run --rm --no-deps telemetry /otel-lgtm/otelcol-contrib/otelcol-contrib validate --config=/otel-lgtm/otelcol-config.yaml
docker compose -p team2-telemetry-check -f observability/compose.yaml up -d
```

The service and all three Grafana data source health endpoints returned 200.
Prometheus queries returned all four operations, and Loki/Tempo returned the
correlated records. The test backend was stopped after evidence capture. The
snapshot remains usable without the running backend.

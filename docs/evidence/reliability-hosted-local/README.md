# Local hosted reliability integration — 2026-11-11

**SDK-controlled/local only. Not deployed Google verification, seven days of
history, Slack delivery, an independent recovery or a game day.**

## What ran

Source: `0e2b19d3ce0075edea6296c67fa2c4241cb52343`, merging
`assgn2-ms3-submission@692597c` into #72. This includes merged #73 telemetry and
#75 hosting. [metrics.json](metrics.json) records SHA-256 hashes of the actual
hosting, factory, middleware, telemetry, provider and rule files used.

- Actual `create_hosted_app()` startup/shutdown, hosted access checks, shared Get
  route/validation, application/cache and Google provider translation ran.
- Only the Google SDK client was controlled; no real OAuth refresh, Google calls,
  cloud resources or provider writes occurred. Runtime credentials were synthetic
  and confined to a temporary directory.
- The real `Telemetry` constructor/lifespan used an injected periodic OTLP HTTP
  metric reader aimed at native Prometheus **3.16.0** on ephemeral loopback.
  This bypasses the need for a separate collector; it does **not** verify deployed
  collector configuration or log/trace transport. All request metrics were
  produced by the actual hosted middleware, not inserted as fake time series.
- Three batches each exercised: 200, contract-correct missing-event 404, provider
  403, malformed provider data -> 502, provider 503, invalid input -> 422, hosted
  access rejection -> 403, and a 200 whose SDK call took at least 1.05 seconds.
  Total: **24 HTTP requests, 18 controlled SDK calls, zero external Google calls**.
  Invalid/unauthorized requests never executed an SDK call.
- Each batch force-flushed metrics and waited at least one second. The first
  batch established cumulative samples; subsequent batches changed them. The
  actual rules evaluated, and `make reliability-report` returned all ten metrics.
- Assertions verified availability `3/7`, latency `6/7`, negative remaining
  budgets, source counters totaling 24, healthy recording rules, and cleared
  hosted readiness/access state on shutdown. Temporary Prometheus/storage and
  synthetic runtime credentials were removed after the check.

## Recorded values

Capture: **2026-11-11T01:47:59Z–01:48:42Z**. Report evaluation timestamp:
`1794361722` (**2026-11-11T01:48:42Z**). Configured window: rolling 604800 seconds;
**actual history is only this short run**. `full_window_coverage_verified` is false.

| SLI | Numerator | Denominator | Value | Allowed bad | Remaining budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| Availability | 9 | 21 | 0.42857142857142855 | 0.21 | -11.79 |
| Latency | 18 | 21 | 0.8571428571428571 | 1.05 | -1.95 |

These deliberate failures overspend both budgets; they say nothing about live
service reliability. `increase` extrapolates cumulative samples, so its estimates
are not a literal count of the two post-warmup batches.

## Repeat the boundary checks

`make test` / `make check` include seven credential-free cases in
[`tests/telemetry/test_hosted_reliability.py`](../../../tests/telemetry/test_hosted_reliability.py).
They use the actual hosted factory and real in-memory SDK metric reader to
verify the outcome/release labels and inclusive 1-second histogram boundary.
They complement, rather than replace, the existing hosted lifecycle regression.
In an isolated copy of the merged source, restoring only pre-fix
`f7d60dc:app/hosting.py` made all seven fail; the fixed hosted factory passes.

To repeat the native export capture, follow the
[earlier loopback export protocol](../reliability-local/README.md#repeat-the-export-integration),
but use `create_hosted_app()` with temporary synthetic runtime configuration and
an SDK-controlled client, not a synthetic HTTP route. Inject the OTLP metric
reader via the real `Telemetry` constructor as above. Run the eight cases in
`metrics.json` three times with unique synthetic event IDs to avoid cache hits;
allow the rule group to evaluate and invoke `make reliability-report`. Stop the
local process and remove its temporary storage/credentials even on failure.

Live collector connectivity, real Google responses, protected Slack transport,
backend history, independent runbook recovery and the game day remain unverified.

# Calendar telemetry

## Runtime configuration

Instrumentation is initialized by the FastAPI lifespan. Set:

| Variable | Meaning |
|---|---|
| `CALENDAR_RELEASE` | Immutable deployed commit SHA/release identifier; 1–80 letters, digits, `.`, `_`, `-`. Defaults to `development` for local work. Deployment must set this. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP collector base URL, e.g. `http://127.0.0.1:4318`. `/v1/metrics`, `/v1/logs`, `/v1/traces` are appended. Without it, bounded asynchronous JSON request logs go to stdout; metrics/traces are not exported. |

Use the standard OTLP headers/certificate environment variables when a protected
collector requires them; keep values outside source control. Do not put secrets
in endpoint URLs. This implementation uses HTTP/protobuf explicitly; generic
protocol or signal endpoint overrides are not its configuration interface.

Run with Uvicorn access logging disabled so raw event paths do not appear in a
second, unstructured access log:

```bash
uv run --locked uvicorn app.main:app --no-access-log --workers 1
```

The supplied backend configuration assumes one service process. Before running
multiple workers/replicas, the deployment owner must attach a trusted unique
`service.instance.id` resource at ingestion and preserve separate metric streams;
otherwise cumulative counters from processes with the same identity collide.
Do not use event IDs or request IDs to identify metric streams.

Invalid telemetry configuration produces the static `telemetry_failure`
diagnostic and does not prevent the API starting. Check telemetry after rollout:
an API response alone does not prove export works. No global auto-instrumentation
is installed. Do not additionally enable generic HTTP/body/SDK debug capture.

### Hosted entry point integration

The infrastructure owner must compose the hosted startup context with the
existing `application.router.lifespan_context`, entering that original context
for the entire hosted lifespan. Replacing it outright discards telemetry
initialization and shutdown. Register `CalendarTelemetryMiddleware` last so it
wraps the hosted access middleware: denied core requests must still produce an
outcome record and request count, while health probes remain excluded.

Tests in `tests/telemetry/test_http_telemetry.py` verify lifespan composition and
measurement of early access rejections using this ordering. The hosted container
entry point is integrated with release configuration and protected collector
connectivity; the retained public dashboard and game-day evidence demonstrate
deployed export. Controlled tests continue to cover access rejection, successful
request export, and shutdown without requiring cloud credentials.

## Signal schema and Level 4 handoff

Operation names are exactly **Create**, **Get**, **Replace**, **Delete**. The HTTP
middleware recognizes `POST /events` and `GET/PUT/DELETE /events/{event_id}` before
validation. Unmatched unrelated paths and optional extensions are excluded.
The four existing CRUD routes and the Google provider from `assgn2-ms3-submission`
at shared-contract integration revision `9e663a9` are
preserved. Their real operations use `provider_span("Create")`, `provider_span("Get")`,
`provider_span("Replace")`, and `provider_span("Delete")`; cached GETs have no
outbound span. PUT retains its fresh Get preflight span before the Replace span.
Provider response validation is included so invalid provider data also marks the
corresponding provider span as failed. No contract or retry behavior is changed.

| OTLP instrument | Prometheus name with standard suffix translation | Meaning |
|---|---|---|
| `calendar.requests` | `calendar_requests_total` | Completed HTTP requests, including rejected input/errors |
| `calendar.errors` | `calendar_errors_total` | HTTP errors and unexpected success/redirect statuses |
| `calendar.request.duration` (`s`) | `calendar_request_duration_seconds_bucket`, `_sum`, `_count` | Request latency distribution, from middleware entry through response completion |
| `calendar.worker.utilization` | `calendar_worker_utilization_ratio` | Borrowed AnyIO thread tokens / actual configured total tokens |
| `calendar.worker.capacity` | `calendar_worker_capacity` | Actual total worker tokens, the saturation denominator |

Request metrics have only `operation`, `outcome`, `release` dimensions. Worker
gauges have only `release`: the pool is shared across operations and must not be
summed four times. OpenTelemetry resource attributes are restricted to service
name/version. Request/trace IDs appear in logs, traces, and histogram exemplars,
never metric labels. Each instrument has a 256-series aggregation limit.

Outcomes follow the actual response status:

| Status | Outcome |
|---|---|
| Create 201, Get 200, Replace 200, Delete 204 | `success` |
| Other 2xx/3xx | `unexpected_status` |
| 400, 422 | `invalid_input` |
| 403 | `access_denied` |
| 404 | `not_found` |
| 502 | `provider_error` |
| 503 | `provider_unavailable` |
| Other 4xx | `client_error` |
| Other 5xx | `application_error` |

The restored baseline uses the tagged `calendar-contract` package
`v0.1.0-rc.1` (`1c1cad7a0732ddb242a05400d8833d94e4422424`). All four core operations use its
shared error model: provider permission failures become 403 `access_denied`,
missing events 404 `not_found`, invalid provider responses 502 `provider_error`,
and temporary read failures 503 `provider_unavailable`. Provider spans and their
failure records use the translated bounded shared category too. Unexpected
application exceptions remain `application_error`.

The shared-contract completion in PR #76 supplies 422 for invalid JSON values or
path/query input, 400 for malformed JSON, and shared error envelopes with
`retryable`. Explicit quota rejection can produce 503 for all core operations;
uncertain write failures remain 502 with `retryable: false`, without retries.
This telemetry issue preserves those merged semantics rather than forking the
shared contract or changing provider behavior. Listing and PATCH retain their
supported extension behavior.

For the Level 4 owner, `Get` success now means **exactly HTTP 200**. A Get 201,
204, or redirect is `unexpected_status` and increments the error counter; it must
not count as good availability. Metric names, existing outcome categories, and
histogram buckets are otherwise unchanged. The 1-second histogram bucket is
upper-inclusive: `le="1"` measures **<= 1s**, not strict < 1s.

There is one JSON request outcome record with `operation`, `outcome`, `status`,
`release`, `request_id`, `trace_id`, and `duration`. Handled responses include a
generated `X-Request-ID` header; client-supplied IDs are not reflected. An
unhandled HTTP 500 generated outside the middleware may lack this header, but
still has its outcome record and trace. Provider failures additionally emit a
sanitized record at the failing call, without exception text or status guesses.

Each request has a SERVER span `calendar.<Operation>`. Google execution has a
nested CLIENT span `google.calendar.<Operation>`. Their shared trace ID and
parent/child timing show provider time separately from the surrounding
application/authentication/translation/serialization work. Only W3C `traceparent`
is accepted; baggage is ignored. Automatic exception events and status
descriptions are disabled, because exception messages/stacks may contain provider
data. No body, raw URL, event ID, query, authorization header, credential, title,
description, or provider response is attached.

Provider-span evidence is retained in
[the hosted SDK-controlled OTLP capture](evidence/reliability-hosted-local/README.md)
and is verified by `tests/telemetry/test_calendar_operations.py`. Unlike the
bounded game-day fault, those ordinary SDK-backed requests cross the Google
boundary and therefore contain the expected `google.calendar.<Operation>` child
span.

The Level 4 owner can use the counter outcomes to select eligible requests and
server failures, and histogram buckets to calculate latency compliance. For
example, these are building blocks, **not an adopted SLO policy**:

```promql
# Traffic by operation/release
sum by (operation, release) (rate(calendar_requests_total[5m]))
# Server failures (do not treat all calendar_errors_total as unavailability)
sum(rate(calendar_requests_total{outcome=~"application_error|provider_error|provider_unavailable"}[5m]))
# Fraction of all recorded requests completing within 1 second
sum(rate(calendar_request_duration_seconds_bucket{le="1"}[5m]))
/
sum(rate(calendar_request_duration_seconds_count[5m]))
```

Agree eligibility, `access_denied` treatment, latency threshold, target/window,
and zero-traffic behavior with the reliability owner. Missing telemetry is not
evidence of zero errors. Alerting/SLO policy and destinations remain outside this
issue. No message has been sent to another teammate by this implementation.

## Bounded export and failure behavior

Traces and logs each use a background batch processor with a **512-record
queue**, **64-record batches** and a two-second exporter network timeout. Queue
overflow drops telemetry rather than waiting for a backend. Metrics aggregate
locally with bounded labels/series and export every ten seconds; they do not
accumulate a queue of request bodies or per-request measurements. Shutdown occurs
outside the request/event-loop path. There is no request-time flush.

Failures of individual instruments, log emission, span setup/cleanup, or export
are isolated from application execution. Broad exception catches are restricted
to these optional telemetry boundaries. The application exception itself always
propagates. SDK/backend diagnostics should be restricted to operators.

The example collector adds a 128 MiB memory limiter, maximum 512-record batches,
32-batch export queues, two-second network timeouts, and ten-second retry windows.
Persistent production backend retention and access controls belong to the
infrastructure owner. Telemetry may be lost during an outage; the service does
not buffer indefinitely to guarantee delivery.

## Dashboard and disposable local backend

The provisioned dashboard in
[`observability/calendar-dashboard.json`](../observability/calendar-dashboard.json)
shows p95 latency by operation/outcome, request rate, categorized error rate, shared worker saturation,
worker capacity, and correlated request logs. Release and operation selectors
filter the panels, and release appears in legends/capacity rows. Request/error
panels link to the log panel; expand a record's `trace_id` and choose **View trace**
to open its Tempo trace. Tempo also links back to logs. Histogram exemplars can
link directly to traces where supported by the backend.

The supplied Docker Compose backend is a pinned Grafana LGTM **local/disposable
verification fixture**, not the production infrastructure. It binds Grafana and
OTLP to loopback and mounts no Calendar credentials. It provisions the dashboard
and Prometheus/Loki/Tempo correlation using Grafana's
[documented data source provisioning](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/provision/).

With Docker available:

```bash
docker compose -f observability/compose.yaml config --quiet
docker compose -f observability/compose.yaml up -d
```

Set `CALENDAR_RELEASE` to a local commit identity and
`OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318` in the service environment,
then start Uvicorn as above. Open
`http://127.0.0.1:3000/d/team2-calendar`. Allow at least two metric exports
(roughly 20 seconds) before rate panels have data. Zero traffic produces gaps
rather than fabricated successes. End the local fixture with:

```bash
docker compose -f observability/compose.yaml down
```

The fixture uses disposable container storage; export evidence before teardown.
Never expose its anonymous Grafana or unauthenticated collector to a public
interface. For a deployed service, the infrastructure owner supplies a protected
OTLP collector and persistent backends, and imports the dashboard using matching
data source UIDs (`prometheus`, `loki`, `tempo`). Pin artifact digests and configure
backend retention within that owner's deployment workflow.

## Deployed verification and retained evidence

The service exported deployed telemetry to the retained public dashboard, and the
bounded game day demonstrated traffic, categorized failures, release identity,
alerting, and recovery. The canonical Delivery smoke established real Google
behavior. Nicolas Ollivier independently exercised the deployed Render service and
used its telemetry during the observability demonstration. The repository does not
retain a timestamped transcript proving that the latest committed dashboard JSON
was imported into the hosted Grafana instance or that the complete three-case
explanation below was narrated by an independent teammate.

The retained controlled export in
[`docs/evidence/telemetry-local/`](evidence/telemetry-local/README.md) contains
representative `success`/200, `invalid_input`/422, and
`provider_unavailable`/503 Get records. The success and provider-failure traces
contain a `calendar.Get` SERVER span and a nested `google.calendar.Get` CLIENT
span; the invalid-input trace correctly has no provider span. These artifacts
prove the correlation and signal shape without claiming that the controlled
capture itself came from the deployed service.

### Exported telemetry privacy inspection

The exported log and trace records in
[`correlated-logs-and-traces.json`](evidence/telemetry-local/correlated-logs-and-traces.json)
and the exported series in
[`metrics.json`](evidence/telemetry-local/metrics.json) were manually inspected
before release reconciliation. The records contain the bounded operation,
outcome, status, release, request ID, trace ID, duration, span relationship, and
service resource fields needed for diagnosis. They contain no OAuth/API/bearer
tokens, authorization headers, credential material, event titles or descriptions,
request/response bodies, provider payloads, raw event IDs, raw URLs, or exception
messages.

Request metrics use the bounded `operation`, `outcome`, and `release` labels.
Saturation/capacity series additionally contain bounded service resource labels
such as job, service name, and service version. Request IDs and trace IDs are
correlation fields in logs and traces only; they are not metric dimensions. The
inspection included collector-added resource fields and found no sensitive
Calendar or provider data.

To repeat or retain a timestamped independent three-case exercise:

1. Record deployed release, dashboard URL, UTC window, backend retention expiry,
   and verifier. Use only a designated test calendar and synthetic event data.
2. Produce one normal successful shared request. Capture its `X-Request-ID`,
   status, release and timestamp; clean up any created event.
3. Produce one invalid request, e.g. POST with an otherwise valid synthetic body
   and a blank title, or GET with a blank ID. Confirm 422 `invalid_input`, no
   provider call, and the matching log/HTTP trace. Malformed JSON remains 400.
4. Produce one provider failure in a designated disposable environment, for
   example with a provider identity lacking permission on a test calendar.
   Coordinate the setup with its owner; do not change production permissions or
   inject a destructive failure. Confirm the agreed status, categorized metric,
   sanitized provider failure log, and errored child span. Restore the fixture.
5. For each request, select its operation/release/time on the dashboard, open the
   matching outcome log, follow **View trace**, and compare HTTP/provider spans.
6. A teammate who did not implement this code explains all three requests:
   caller versus service/provider failure, release, status/category, trace
   relationship, and where time was spent. Retain their name/date and findings.
7. Manually inspect at least one **actual exported log and trace** for sensitive
   data, including resource attributes, span events, status descriptions and
   collector-added fields. Automated synthetic privacy tests supplement this
   inspection and do not replace it.
8. Retain sanitized dashboard screenshots/query exports, the three outcome logs,
   traces with span timings, release/request/trace IDs, reviewer notes, and the
   sensitivity review in the team's protected submission evidence location.
   Link these artifacts from the issue/PR. Keep credentials, raw Calendar
   contents, full HTTP payloads and unreviewed exports out of submissions/Git.

For each case retain: `case`, `UTC time`, `release`, `operation`, `HTTP status`,
`outcome`, `request_id`, `trace_id`, dashboard/log/trace artifact links,
independent reviewer, and sensitivity-review result. These steps are an evidence-
retention procedure, not a claim that the latest dashboard revision was imported.

## Automated verification

`tests/telemetry/` exercises all four operation hooks on controlled HTTP routes,
error categorization, validation before provider execution, the actual GET-to-SDK
span relationship, context propagation, exact-once SDK execution, privacy,
histograms/counters, actual worker-capacity ratios, failing instruments, blocked
exporter overflow, and a refused OTLP connection. A local HTTP receiver decodes
actual OTLP/protobuf metrics, logs, and traces for synthetic success/invalid/error
requests and checks correlation and sensitive-data omission.

`test_calendar_operations.py` additionally exercises the **real existing CRUD
routes, application/cache composition and Google provider**, controlling only
the SDK. It checks successful responses, rejected input before provider setup,
403/404/502/503 categories, exact-once SDK execution, PUT preflight spans, invalid
provider responses, safe metadata, and unchanged responses when tracing and
request recording fail. Exact-status tests prevent unexpected 2xx/3xx replies
from appearing as successful operations to the Level 4 consumer.

Run the repository's existing `make check`; those tests are included in normal
credential-free CI. The Compose fixture, collector validation, dashboard rendering,
and local exported metrics/logs/traces were also checked; see the retained
[local synthetic evidence](evidence/telemetry-local/README.md). Deployed dashboard
and game-day evidence is retained under `docs/evidence/reliability-live/` and
`docs/reliability/`. The exported telemetry sensitivity inspection is recorded
above. A timestamped independent narration of all three cases is not retained.

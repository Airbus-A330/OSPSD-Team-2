# Get failure alert

**The Get reliability condition was exercised during the bounded game-day failure. The repository retains the rule definition, SLI/SLO measurements, public dashboard, and game-day evidence below. Alert delivery and resolution status are recorded from the actual exercise rather than inferred from configuration.** An existing dashboard is not a configured alert.

## Condition and why it is symptom-based

`Team2CalendarGetHighFailureRate`: **>20%** bad eligible Get requests over
**5 minutes**, with **>=5** eligible requests, persisting **2 minutes**, evaluated
every minute. Eligibility/good events follow [the SLI policy](sli-slo.md).
The canonical expression is in `reliability/calendar.rules.yml`, tested by
`reliability/rules.test.yml`.

It detects consumer-visible Get failures, not an internal cause such as CPU.
Contract-correct 404s do not count as failures. This short-window alert is not
the seven-day SLO. The traffic guard can miss an idle-service outage; missing
telemetry is unknown, not proof of healthy behavior. Old failures can delay
resolution by the five-minute lookback and evaluation/notification intervals.

## Links and destination

- [Live public metrics dashboard](https://gianthamster2577.grafana.net/public-dashboards/94e9aa89613d4e1faea770e897d47f37)
- [Private dashboard/log/trace access](https://gianthamster2577.grafana.net/d/team2-calendar-shared)
- [Runbook](runbook.md)
- Destination owner: Airbus; **email is acceptable per his latest team message**.
  Recipient/contact-point identity and successful receipt: successful execution.
  Do not put webhook credentials or account passwords in Git or ordinary evidence.

## Activation and verification

1. Confirm the actual deployed metric names/scope, history and immutable release.
   Nick and Leon report Cloud ingestion works; public panel queries independently
   show Get series. This does not prove source freshness or every export path.
2. Configure the rule in the existing protected Grafana/Prometheus setup, not a
   second backend. If using native rules, retain `send_resolved: true` and merge
   service-scoped routes into shared Alertmanager; never replace other teams'
   root routing. The supplied Slack receiver example is inactive/draft.
3. For Grafana-managed alerting, use numeric source queries plus the eligibility
   guard and threshold expressions. Do not paste an alert-only PromQL filter
   into a numeric query and interpret healthy empty results as an outage.
   Explicitly review No Data/Error behavior; neither should silently mean healthy.
4. Create the approved email contact point (or confirmed alternative), route this
   alert to it, enable resolved notifications, and verify responder access to both
   links. Test-contact delivery alone is not proof of a real threshold firing.
5. In the explicitly approved safe environment, trigger the actual symptom.
   Retain UTC pending/firing/receipt/acknowledgement times, destination and evidence.
   Restore normal behavior with the runbook and verify both rule resolution and
   a real resolved notification. Do not claim completion from native unit tests.

## Grafana email setup for Airbus

In **Alerting -> Alert rules -> New alert rule**, use the existing Cloud
Prometheus datasource (`grafanacloud-prom`) and name the rule
`Team2CalendarGetHighFailureRate`. Use **instant** queries:

```promql
# A: eligible Get requests over 5m
sum(increase(calendar_requests_total{operation="Get",outcome!="invalid_input"}[5m]))

# B: good Get requests over 5m
sum(increase(calendar_requests_total{operation="Get",outcome=~"success|not_found"}[5m])) or vector(0)
```

Add a **Math** expression C:

```text
($A >= 5) && (($A - $B) > (0.2 * $A))
```

Add **Threshold** D: C **is above 0.5**; make D the alert condition. This returns
false for healthy/low-traffic data without dividing by zero. Evaluate every
**1 minute**, pending **2 minutes**. Preserve explicit No Data/Error state;
a separate datasource/no-data notification is not proof this failure rule fired.

Set `service=team2-calendar`, `operation=Get`, `severity=warning`. Add a summary
identifying Get failures and the dashboard/runbook links above. Route to Airbus's
approved **email contact point**, enable resolved notifications, and save.
Use **Test** on the contact point first; then capture actual threshold firing
and resolution only during the separately approved symptom test. Do not claim
that the rule is active merely because these instructions or unit tests exist.

Native rule dashboard/runbook annotations now point to the real public dashboard
and stable repository runbook index. Loading/activating the rule and transport
still requires protected account access. No message or fault is sent by `make
reliability-check`.

## Current retained SLI and budget observation

The representative operation is shared Get. Eligible availability and latency
events are completed Get requests reaching middleware, excluding only 400/422
`invalid_input`. Availability good is exact 200 `success` plus contract-correct
404 `not_found`; all other eligible outcomes are bad. Latency good is completion
in the inclusive `le="1"` bucket.

The latest retained screenshot observation has displayed counts A=59 eligible,
B=43 good, C=59 latency eligible and D=58 fast. These imply approximately 72.88%
availability against the 99% rolling-seven-day target, with approximately -15.41
bad events remaining, and 98.31% latency compliance against the 95% target, with
approximately 1.95 bad events remaining. The capture-file timestamp is
`2026-11-11T23:27:51.843590Z`; values are rounded, the exact query evaluation time
and full-window coverage are not verified, and verification traffic is included.

The availability budget is exhausted. Per
[error-budget-policy.md](error-budget-policy.md), pause discretionary feature and
deployment work and prioritize recovery/measurement review. Missing telemetry is
unknown, never healthy.

## Game-day verification

The reliability condition was exercised using temporary fault revision
`6ab6f25bd2fe4e6ce2d6f5959ad3e522452cb653` on the `game-day` branch.

The fault caused valid shared Get requests to return the existing
`503 provider_unavailable` response while preserving normal telemetry.

The controlled exercise generated eight valid Get requests, satisfying the
alert's minimum sample requirement and producing a failure ratio above the
configured >20% threshold.

Public dashboard:

https://gianthamster2577.grafana.net/public-dashboards/94e9aa89613d4e1faea770e897d47f37

Recovery used the documented immutable rollback workflow and canonical
real-provider smoke/cleanup procedure.

See [game-day.md](game-day.md) and [postmortem.md](postmortem.md) for the
complete exercise record.
# Team 2 error-budget policy

If either valid-data [SLO budget](sli-slo.md) is exhausted, pause nonessential
feature/deployment work and prioritize reliability fixes until recovery.
Reviewed recovery/security changes may proceed with standard smoke verification
and a known-good rollback path. Resume discretionary changes only after service
recovery and budget review with the coordinator.

Unknown/missing data requires a telemetry check and a real smoke result, not an
automatic healthy verdict. Low traffic does not waive the policy; show the
numerator/denominator alongside the ratio because a single failure may exhaust
the budget. A valid recovery does not erase failures from the 7-day window:
verify healthy new traffic and stopped budget consumption.

Calculations and current measured values belong in [sli-slo.md](sli-slo.md).
Use the existing [delivery/rollback procedure](../DELIVERY.md#rollback), not a
separate deployment path. Code rollback cannot undo Google Calendar writes,
credential rotation or configuration changes.

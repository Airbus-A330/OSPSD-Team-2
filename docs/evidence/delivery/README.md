# Delivery and recovery evidence

[Local validation](LOCAL_VALIDATION.md) records implementation checks. The live
Delivery and reliability records below establish the external stages; neither
local validation nor a successful build alone is treated as deployment evidence.

## Retained known-good Delivery

| Stage | Actions URL / attempt | Source SHA | Image digest | Smoke / cleanup | Result |
| --- | --- | --- | --- | --- | --- |
| Automatic reviewed merge release | [Run 43064300096](https://github.com/Airbus-A330/OSPSD-Team-2/actions/runs/43064300096) | `7854d695cc2b8e84752ec3b4e4aacd2042125478` | `sha256:97e205b2532e5420035c1e57aa489b09d9efe96be1dbefda2452290f7b4f020c` | Passed / confirmed | SUCCESS |
| Bounded faulty revision | [Fault commit](https://github.com/Airbus-A330/OSPSD-Team-2/commit/6ab6f25bd2fe4e6ce2d6f5959ad3e522452cb653) | `6ab6f25bd2fe4e6ce2d6f5959ad3e522452cb653` | Not retained in repository evidence | Not applicable before recovery | EXPECTED GET FAILURE OBSERVED |
| Restore known-good behavior | See [game-day record](../../reliability/game-day.md) | `7854d695cc2b8e84752ec3b4e4aacd2042125478` | `sha256:97e205b2532e5420035c1e57aa489b09d9efe96be1dbefda2452290f7b4f020c` | Passed / confirmed | SUCCESS |

Run `43064300096` is the retained known-good recovery reference. It is not
mislabelled as the later rollback workflow run. The team confirmed recovery used
the documented Delivery process, restored that known-good behavior, and reran the
same canonical real-provider smoke with cleanup. A separate recovery Actions URL
and the faulty image digest were not retained in repository evidence.

The bounded fault ran only in the approved disposable/test environment. It made
valid Get requests return `503 provider_unavailable` before any provider call,
so the fault itself performed no Calendar writes. Image rollback cannot undo
provider writes made before rollback.

No credentials, OAuth JSON, private Calendar identifiers, raw provider payloads,
or authorization headers are retained here. Downloaded Delivery evidence is kept
under [reliability-live](../reliability-live/README.md); alert, responder, and
postmortem evidence is under [reliability](../../reliability/game-day.md).

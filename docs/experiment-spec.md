# M0 experiment specification

Status: **M0-v1 frozen on 2026-09-24** for future formal collection. Measurement and window parameters are in [m0-v1.toml](../configs/m0-v1.toml); [pilot.toml](../configs/pilot.toml) and all inspected pilot sessions remain historical. The [pilot observations](pilot-observations.md) motivated this protocol but are not an untouched test set. No model result exists yet.

## Research question and scope

Can recent round-trip delay observations on a controlled local network predict the next minute's RTT P95 better than a persistence baseline?

The first experiment measures the path from a MacBook on Ethernet, through a local router/access point, to a Windows PC on Wi-Fi, and back. The PC is a fixed ICMP Echo responder. This setup measures the complete host-to-host round trip; PC Wi-Fi conditions, host scheduling, and ICMP handling can affect the result. Keep the endpoint, route, probe type, payload, and timeout constant within a dataset. The result will describe this setup, not arbitrary internet paths or application latency.

The MacBook collects and later trains/evaluates locally. The Windows PC is needed during collection and live validation, but not for offline training or replay. No additional server or GPU is required.

## Probe and prediction definition

| Item | M0-v1 value | Meaning |
| --- | --- | --- |
| Probe | ICMP Echo, 56-byte payload | One request to the same PC address per scheduled slot |
| Cadence | 1 scheduled probe per second | Save actual start time and scheduling delay |
| Timeout | 800 ms | No reply by this limit is a timeout, not an RTT of 800 ms |
| Session | 15 minutes, first 60 seconds warm-up | One scenario and stable topology per session |
| Observation window | 60 consecutive probe slots | At decision slot `t`: slots `t-59` through `t` |
| Forecast window | Next 60 probe slots | Slots `t+1` through `t+60`; no future observations as inputs |
| Window stride | 10 slots | Reduces redundant examples; windows still overlap |
| Target | P95 of successful future RTTs, in ms | Nearest-rank percentile: sorted value at rank `ceil(0.95 × n)` |

M0-v1 window policy: require at least 57 `ok` probes in **each** 60-slot observation and forecast window. Treat `timeout` and `send_error` with `error_code=ping_process_timeout` as missing RTT observations, not as measured packet loss or RTT values. Reject a window containing `missed_slot`, any other `send_error`, or a documented sleep/time discontinuity. Thus no more than three missing RTTs are allowed in either window. Preserve every rejected window and its reasons. This rule was selected after inspecting pilot sessions; its utility and coverage must be assessed on independent formal sessions without retuning against the final test set.

Missing replies never become `0 ms`, `800 ms`, or another fabricated RTT. The target remains the P95 of **successful** future RTTs only; it is not a loss-aware quality score. Report `timeout` and `ping_process_timeout` counts separately, the accepted-window fraction, and the fraction of windows with no missing probes. Otherwise the revised policy could conceal degraded availability or bias the target toward responsive periods.

The 60-second warm-up is excluded from observation windows. A full 15-minute session schedules 900 probes at offsets 0 through 899 seconds and ends at offset 900 seconds. Probe timing uses the collector's monotonic clock.

The first feature set is RTT history and a status mask that distinguishes `ok`, `timeout`, and `ping_process_timeout`. Other statuses invalidate the window. Scenario labels are for stratified reporting, not model inputs; future load schedules, future statuses, and future measurements are forbidden inputs. Additional host/network counters may be considered after the pilot, with their collection and availability defined before model comparison.

## Scenarios and controls

The scenarios are `idle`, sustained `upload`, sustained `download`, and `burst`. Traffic is between the two local machines. Record the traffic generator and settings before each session; do not assume the intended load was achieved. Keep the MacBook Ethernet connection, PC Wi-Fi position/band/access point, power state, and VPN state as stable as practical. Save changes and interruptions in session notes. A session contains only one declared scenario; start a new session when changing it.

`upload` and `download` are defined from the MacBook's perspective. Use iperf2 TCP with one Mac-to-PC flow for sustained `upload`, four PC-to-Mac flows for sustained `download`, and one Mac-to-PC flow per `burst` pulse. Keep the flow count, iperf versions, socket-buffer settings, and direction fixed within each profile; do not change Windows global TCP settings to run the experiment. Calibrate each direction with three separate 30-second uncapped trials using the **same flow profile** as its sustained scenario. For each trial, take the median receiver-side per-second aggregate throughput after the first five seconds; use the median of the three trial medians as that profile's capacity. Sustained aggregate target is 70% of this capacity. With four download flows, the iperf2 client `-b` value is **per flow**: set it to aggregate target / 4 and verify the receiver's `[SUM]` rate. Mac-to-PC bursts start at 90% of the one-flow Mac-to-PC capacity. The generator seed, planned and actual pulse times, tool versions, target rate, and achieved throughput are experimental evidence. See [pilot-plan.md](pilot-plan.md) for commands.

Preserve both ends' iperf logs and record the actual load start/end UTC times; the generated load must cover the whole 900-second collector interval. For a controlled sustained-load session, the receiver-side mean aggregate throughput over the collector-overlap period must be within 15% of the predeclared target, and no complete 60-second overlap block may average below 75% of target. These are operational adherence gates, not model performance claims. For `burst`, retain the schedule, completed-pulse count, and receiver-side pulse evidence; report actual pulse throughput separately from the requested rate. Do not change load settings mid-session. A session with missing load evidence, a failed adherence gate, or a newly observed capacity regime remains raw pilot/diagnostic evidence but is excluded from the controlled scenario set until the regime is documented and a new session is collected. Do not silently recalibrate each session to hide a change in conditions.

Keep both hosts awake and on power. Compare adjacent wall-clock and monotonic probe intervals; if their difference exceeds two seconds, flag a clock/sleep discontinuity and reject all windows spanning it. A confirmed sleep invalidates a controlled formal session. Keep `missed_slot` distinct from allowed missing RTTs.

The pilot was for feasibility and protocol revision. Do not use it as the final held-out test after inspecting it or changing the specification. Define formal collection volume and scenario repetition in M1 before assigning the held-out test sessions.

## Data split and evaluation plan

Assign **whole formal sessions** to train, validation, and test before creating windows. Keep all windows from one session in one split. Prefer later collection days for the final test when each scenario has enough sessions; otherwise document the narrower generalization claim. Freeze the test assignment before feature selection or tuning. Fit any imputation or normalization on training sessions only.

The primary baseline predicts future RTT P95 with the observed 60-slot P95 of successful RTTs, using the same validity rules. A rolling-average baseline may be added in M2. Report per-session and per-scenario MAE in ms, plus signed bias, P95 absolute error, valid-window coverage, fully observed-window coverage, separate `timeout` and `ping_process_timeout` rates, and the number of independent sessions. Aggregate by giving sessions equal weight; do not treat overlapping windows as independent replicates. Compare the model and baselines on identical valid windows.

The project may find that the target is poorly predictable from past RTT alone. That is an acceptable experimental outcome; model complexity will be justified by held-out results.

## M0 exit criteria

1. Review the raw data contract and pilot procedure linked below.
2. Run the pilot after the M1 collector exists, checking timing, timeouts, scenario separation, and label coverage.
3. Record any parameter changes and freeze a versioned specification before formal collection.

M0-v1 decision: retain 1 Hz cadence and the 800 ms ICMP reply timeout, freeze the 57/60 rule while keeping `ping_process_timeout` distinct from confirmed packet loss, use the four-flow PC-to-Mac download profile with per-flow pacing, and enforce the load and time-continuity checks above. The pilot's missing PC receiver-side upload/burst logs limit what can be claimed about those historical sessions; both-end logs are required for new controlled sessions. Independent validation, formal data volume, and model comparisons belong to later milestones, not to the inspected M0 pilot.

See [data-contract.md](data-contract.md) for record definitions and [pilot-plan.md](pilot-plan.md) for the pilot procedure.

## Measurement references

- [RFC 2681: A Round-trip Delay Metric for IPPM](https://www.rfc-editor.org/rfc/rfc2681.html) defines round-trip delay, timeout considerations, and measurement uncertainty.
- [scikit-learn: Cross-validation and time-series data](https://scikit-learn.org/stable/modules/cross_validation.html) explains why ordinary random splitting can give misleading estimates for ordered observations.

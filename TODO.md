# NetPulse TODO

## M0 — Define the experiment

- [x] Draft the prediction target, windows, probe cadence, and timeout in [the experiment spec](docs/experiment-spec.md).
- [x] Draft raw fields, units, timestamps, missing-value rules, and session metadata in [the data contract](docs/data-contract.md).
- [x] Draft session-level split rules, baselines, and evaluation metrics.
- [x] Document device roles and [the pilot procedure](docs/pilot-plan.md).
- [x] Run and review exploratory idle, upload, download, and burst sessions in [pilot observations](docs/pilot-observations.md).
- [x] Resolve pilot quality findings and freeze the versioned [M0-v1 specification](docs/experiment-spec.md) before formal collection.

## M1 — Collect and inspect data

- [x] Build the MacBook ICMP pilot collector from the M0 data contract.
- [x] Build a logged burst load generator; historical M0 used iperf2 and the draft two-MacBook pilot uses iperf3.
- [x] Prepare scripts for two-direction iperf3 calibration and paired upload/download/burst pilot runs.
- [x] Review two 900-second idle sessions; no iperf3 client ran, and the target only had an iperf3 server listening. Preserve their RTTs.
- [x] Separate the unverified 571/882 Mbit/s topology figures from these idle sessions; they were not produced by the idle runs.
- [x] Repeat Wi-Fi-path idle without the iperf3 server; the RTT tail persists and all 900 probes succeeded.
- [x] Document the Wi-Fi-path idle RTT tail as a persistent observation; do not claim a controlled low-latency Wi-Fi reference.
- [x] Calibrate both directions and review upload, download, and burst sessions in the [two-MacBook pilot](docs/mac-mac-iperf3-pilot-v1.md).
- [x] Review load adherence and probe/window quality; freeze the separate [two-MacBook formal v1 protocol](docs/mac-mac-iperf3-formal-v1.md) before collection.
- [ ] Record quality-checked formal sessions across idle, upload, download, and burst-traffic scenarios.
- [ ] Validate raw data and produce a distribution and quality report.

## M2 — Establish baselines

- [ ] Implement last-value and rolling-average predictors.
- [ ] Train simple linear and tree-based baselines.
- [ ] Evaluate by held-out session and scenario; record errors and failure cases.

## M3 — Train a small neural model

- [ ] Implement a PyTorch MLP and reproducible training pipeline.
- [ ] Save model configuration, feature schema, normalization parameters, and weights.
- [ ] Compare with baselines on the same held-out sessions.

## M4 — Explore temporal modeling

- [ ] Try one small temporal architecture if the data and baselines justify it.
- [ ] Compare accuracy, model size, inference latency, and robustness.

## M5 — Validate runtime behavior

- [ ] Implement replay-based inference on the MacBook.
- [ ] Validate live predictions with a controlled test endpoint when needed.
- [ ] Record operating limits and a reproducible demo.

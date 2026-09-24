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
- [x] Add a logged Mac-to-PC burst load generator and define profile-specific rate calibration rules.
- [ ] Verify the Windows PC as a controlled ICMP test endpoint and prepare traffic generation.
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

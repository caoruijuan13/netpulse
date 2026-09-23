# NetPulse TODO

## M0 — Define the experiment

- [ ] Specify the prediction target, observation window, forecast horizon, and sampling rate.
- [ ] Define telemetry fields, units, timestamps, missing-value rules, and session metadata.
- [ ] Define session-level train/validation/test splits and evaluation metrics.
- [ ] Document the MacBook and Windows PC roles for local-network experiments.

## M1 — Collect and inspect data

- [ ] Build a collector for the MacBook and a controlled test endpoint on the Windows PC.
- [ ] Record independent sessions across idle, upload, download, and burst-traffic scenarios.
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

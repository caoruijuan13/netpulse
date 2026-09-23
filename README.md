# NetPulse

Local network performance prediction and regression analysis engine.

NetPulse is a lightweight, on-device model that continuously learns 
from your system's network telemetry — predicting throughput, latency, 
packet loss, and jitter before they degrade, detecting anomalies with 
root-cause attribution, and feeding structured decisions into an Agent 
Runtime for closed-loop optimization.

## Why

Network performance issues are reactive today: you notice only after 
users complain. NetPulse shifts this to proactive — by modeling the 
relationship between system-level features (CPU load, queue depth, 
retransmission rate, congestion window) and network QoS metrics, it 
predicts degradation 30 seconds to 5 minutes in advance, with 
confidence intervals and explainable attributions.

## What it does

1. **Continuous Telemetry Ingestion** — collects multi-variate time-series 
   from tshark, ss, /proc/net, and system metrics at configurable intervals.

2. **Multi-target Regression** — a compact neural model (MLP → TCN upgrade 
   path) predicts RTT, throughput, loss rate, and jitter for the next N steps.

3. **Residual-based Anomaly Detection** — separates normal fluctuation from 
   real degradation using prediction error distribution, not static thresholds.

4. **Root-cause Attribution** — SHAP-based feature contribution ranking 
   answers "which variable caused this anomaly" (e.g., DNS timeout vs. 
   bufferbloat vs. remote congestion).

5. **Structured Output Contract** — every prediction and anomaly report 
   conforms to a strict JSON schema, consumable directly by an Agent 
   Runtime without parsing or validation.

6. **Closed-loop Ready** — anomaly reports trigger actionable suggestions 
   (DNS switch, congestion algo change, connection reset) that the Runtime 
   executes with permission gates and rollback.

## Architecture

    ┌─────────────────────────────────────────────────┐
    │              Telemetry Collector                 │
    │  (tshark · ss · /proc/net · CPU · mem)          │
    └───────────────────┬─────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────┐
    │           Feature Engineering                    │
    │  (windowing · normalization · drift detection)  │
    └───────────────────┬─────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────┐
    │        NetPulse Model (MLP → TCN)               │
    │  input:  [feature_vector × window_size]         │
    │  output: {predictions, confidence, version}     │
    └───────────────────┬─────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────┐
    │      Anomaly Detector + Attributor               │
    │  (residual analysis · SHAP · action suggester)  │
    └───────────────────┬─────────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────────┐
    │      Structured Output (JSON Schema)             │
    │  → consumed by Agent Runtime for execution      │
    └─────────────────────────────────────────────────┘

## Why not just use Prometheus / Grafana / DataDog?

They alert after the fact. NetPulse predicts before. And unlike 
cloud APM tools, it runs entirely on your machine — no data leaves 
your domain, no subscription, no black-box model.

## Roadmap

- [ ] v0.1 — MLP regression baseline on simulated data (Noxim / Caliper)
- [ ] v0.2 — Residual anomaly detection + SHAP attribution
- [ ] v0.3 — TCN upgrade for temporal pattern capture
- [ ] v0.4 — Structured output decoder (JSON Schema enforced)
- [ ] v0.5 — Agent Runtime integration (action dispatch + rollback)
- [ ] v0.6 — Online learning / drift adaptation
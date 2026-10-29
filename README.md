# NetPulse

NetPulse is a learning project focused on local network performance prediction. It aims to collect time-series data from repeatable network experiments, establish simple prediction baselines, and train small neural models to assess whether short-term performance changes can be predicted.

The project combines network performance testing with hands-on small-model development. Its focus includes data collection, time-window construction, regression training, evaluation across independent experiment sessions, and inference cost measurement. Model choices will be guided by experimental results.

## Current status

M0 is complete for the original Windows/iperf2 setup: its [M0-v1 experiment specification](docs/experiment-spec.md), [raw data contract](docs/data-contract.md), and [collection procedure](docs/pilot-plan.md) remain frozen for that setup. Exploratory sessions for all four scenarios—idle, upload, download, and burst—are reviewed in the [pilot observations](docs/pilot-observations.md). The pilot data are not an untouched held-out test set. Formal data collection, training, evaluation, and live prediction have not been completed; there is no model performance result yet.

M0-v1 uses the previous 60 seconds of observations to predict successful-reply RTT P95 over the next 60 seconds. Those rules remain frozen for the historical Windows topology. The separate [two-MacBook formal v1 protocol](docs/mac-mac-iperf3-formal-v1.md) is now frozen for the new path, with no discarded warm-up and a preassigned 32-session collection plan. No formal sessions or model results have been collected yet.

A separate [two-MacBook iperf3 pilot](docs/mac-mac-iperf3-pilot-v1.md) established the current collection setup: the development MacBook collects on Wi-Fi and the older MacBook responds/serves on Ethernet. Idle, upload, download, and burst trial sessions have been reviewed. The Wi-Fi-path idle RTT tail persisted across repeats and is a documented property of this setup, not a reason to relabel those observations. Previously associated 571 and 882 Mbit/s figures are not throughput from idle runs; their source remains unverified. The historical Windows/iperf2 M0-v1 and the opposite-link two-Mac draft remain intact.

The [formal collection wrapper](scripts/mac_mac_iperf3_formal.sh) uses the frozen configuration and requires a preassigned slot ID. The pilot [calibration and loaded-trial helper](scripts/mac_mac_iperf3_trial.sh) remains available for exploratory runs. Run a new two-direction calibration before formal loaded sessions; historical throughput figures are not their target rates.

## Planned workflow

1. **Define the experiment:** Specify the prediction target, sampling method, data fields, missing-value rules, and evaluation metrics.
2. **Collect data:** Record independent experiment sessions on a controlled local network, including idle, upload, download, and burst-traffic scenarios.
3. **Establish baselines:** Compare last-value, rolling-average, simple linear, and tree-based predictors.
4. **Train a small model:** Start with an MLP; explore one temporal model if the data and baseline results justify it.
5. **Validate inference:** Replay collected data first, then run live prediction experiments as needed. Measure error, latency, and resource use.

Training, validation, and test sets will be split by complete experiment session so that adjacent time windows do not appear in different sets. Models will be compared with baselines on the same held-out sessions, with results examined separately for each network scenario.

## Experiment setup

- **Newer MacBook on Wi-Fi:** Development machine for data collection, traffic generation, training, and offline inference in the current pilot.
- **2015 Intel MacBook on Ethernet:** ICMP responder and iperf3 server in the current pilot; the older Windows PC remains the historical M0 pilot endpoint.
- **Local router or access point:** Connects the two machines for network experiments.

Offline training and data replay require only the MacBook. Live network experiments also require a controlled test endpoint. A dedicated GPU or continuously running server is not required at this stage.

## Project structure

```text
netpulse/
├── configs/          # Historical M0-v1, two-MacBook pilot, and frozen formal parameters
├── docs/             # M0 experiment, data, and pilot specifications
├── scripts/          # Two-MacBook pilot and formal collection helpers
├── src/netpulse/     # Pilot collector and iperf3 burst generator; later model code
├── tests/            # Pilot tool tests; later model tests
├── TODO.md           # Stages and tasks
└── pyproject.toml    # Python project metadata
```

See the [TODO](TODO.md) for the planned tasks and stages.

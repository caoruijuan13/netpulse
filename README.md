# NetPulse

NetPulse is a learning project focused on local network performance prediction. It aims to collect time-series data from repeatable network experiments, establish simple prediction baselines, and train small neural models to assess whether short-term performance changes can be predicted.

The project combines network performance testing with hands-on small-model development. Its focus includes data collection, time-window construction, regression training, evaluation across independent experiment sessions, and inference cost measurement. Model choices will be guided by experimental results.

## Current status

M0 is complete: the [M0-v1 experiment specification](docs/experiment-spec.md), [raw data contract](docs/data-contract.md), and [collection procedure](docs/pilot-plan.md) are frozen for new controlled sessions. Exploratory sessions for all four scenarios—idle, upload, download, and burst—are reviewed in the [pilot observations](docs/pilot-observations.md). The pilot data are not an untouched held-out test set. Formal data collection, training, evaluation, and live prediction have not been completed; there is no model performance result yet.

M0-v1 uses the previous 60 seconds of observations to predict successful-reply RTT P95 over the next 60 seconds. Its measurement and window rules are frozen for the next collection phase, but the time windows are a starting design, not a validated optimum.

## Planned workflow

1. **Define the experiment:** Specify the prediction target, sampling method, data fields, missing-value rules, and evaluation metrics.
2. **Collect data:** Record independent experiment sessions on a controlled local network, including idle, upload, download, and burst-traffic scenarios.
3. **Establish baselines:** Compare last-value, rolling-average, simple linear, and tree-based predictors.
4. **Train a small model:** Start with an MLP; explore one temporal model if the data and baseline results justify it.
5. **Validate inference:** Replay collected data first, then run live prediction experiments as needed. Measure error, latency, and resource use.

Training, validation, and test sets will be split by complete experiment session so that adjacent time windows do not appear in different sets. Models will be compared with baselines on the same held-out sessions, with results examined separately for each network scenario.

## Experiment setup

- **MacBook on Ethernet:** Primary development machine for data collection, processing, training, and offline inference.
- **Older Windows PC on Wi-Fi:** An on-demand, controlled network test endpoint for data collection and live validation.
- **Local router or access point:** Connects the two machines for network experiments.

Offline training and data replay require only the MacBook. Live network experiments also require a controlled test endpoint. A dedicated GPU or continuously running server is not required at this stage.

## Project structure

```text
netpulse/
├── configs/          # Historical pilot and frozen M0-v1 parameters
├── docs/             # M0 experiment, data, and pilot specifications
├── src/netpulse/     # Pilot collector and burst generator; later model code
├── tests/            # Pilot tool tests; later model tests
├── TODO.md           # Stages and tasks
└── pyproject.toml    # Python project metadata
```

See the [TODO](TODO.md) for the planned tasks and stages.

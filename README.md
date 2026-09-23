# NetPulse

NetPulse is a learning project focused on local network performance prediction. It aims to collect time-series data from repeatable network experiments, establish simple prediction baselines, and train small neural models to assess whether short-term performance changes can be predicted.

The project combines network performance testing with hands-on small-model development. Its focus includes data collection, time-window construction, regression training, evaluation across independent experiment sessions, and inference cost measurement. Model choices will be guided by experimental results.

## Current status

The project currently contains a Python package skeleton and a [TODO](TODO.md). Data collection, training, evaluation, and live prediction have not been implemented. There is no runnable prediction demo or model performance result yet.

The first stage will define the prediction task. One candidate is to use the previous 60 seconds of observations to predict RTT P95 over the next 60 seconds. The sampling rate, metric definition, probing method, and evaluation criteria will be decided in M0. These time windows are a starting proposal, not a validated optimum.

## Planned workflow

1. **Define the experiment:** Specify the prediction target, sampling method, data fields, missing-value rules, and evaluation metrics.
2. **Collect data:** Record independent experiment sessions on a controlled local network, including idle, upload, download, and burst-traffic scenarios.
3. **Establish baselines:** Compare last-value, rolling-average, simple linear, and tree-based predictors.
4. **Train a small model:** Start with an MLP; explore one temporal model if the data and baseline results justify it.
5. **Validate inference:** Replay collected data first, then run live prediction experiments as needed. Measure error, latency, and resource use.

Training, validation, and test sets will be split by complete experiment session so that adjacent time windows do not appear in different sets. Models will be compared with baselines on the same held-out sessions, with results examined separately for each network scenario.

## Experiment setup

- **MacBook:** Primary development machine for data collection, processing, training, and offline inference.
- **Older Windows PC:** An on-demand, controlled network test endpoint for data collection and live validation.
- **Local router or access point:** Connects the two machines for network experiments.

Offline training and data replay require only the MacBook. Live network experiments also require a controlled test endpoint. A dedicated GPU or continuously running server is not required at this stage.

## Project structure

```text
netpulse/
├── configs/          # Planned experiment configurations
├── src/netpulse/     # Planned project code
├── tests/            # Planned tests
├── TODO.md           # Stages and tasks
└── pyproject.toml    # Python project metadata
```

See the [TODO](TODO.md) for the planned tasks and stages.

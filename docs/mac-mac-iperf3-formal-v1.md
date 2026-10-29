# Two-MacBook iperf3 formal collection v1

Status: **frozen before formal collection** on 2026-10-22. The executable configuration is [`configs/mac-mac-iperf3-v1.toml`](../configs/mac-mac-iperf3-v1.toml). This is a separate experiment from the historical Mac-Ethernet/Windows-Wi-Fi M0-v1 and the inspected two-MacBook pilots. Do not use pilot sessions as the held-out test set.

## Measurement and acceptance

The newer MacBook runs ICMP collection and the iperf3 client over Wi-Fi (`en0` in the trial); the 2015 Intel MacBook answers ICMP and runs the iperf3 server over Ethernet (`192.168.1.151` in the trial). Both stay on power, open, and awake, with fixed position/AP/band and VPN off. The server uses `caffeinate -i` during loaded sessions. Record any environmental deviation. Keep port 5201 and ICMP available only on the private experiment network.

Each session contains 900 one-second ICMP slots with a 56-byte payload and 800 ms reply timeout. There is **no discarded warm-up**. A 60-slot history predicts the following 60-slot RTT P95; stride is 10 slots, yielding 79 candidate windows per complete session. Each side of a window needs at least 57 successful RTTs. Preserve missing/error statuses and rejected-window reasons; do not impute them as RTTs. Scenario labels and future burst schedules are not model inputs.

For one-stream `upload` (Wi-Fi → Ethernet) and `download` (Ethernet → Wi-Fi), use 70% of the corresponding receiver-side calibration capacity. For one-stream Wi-Fi → Ethernet burst pulses, use 90% of upload capacity. Calibrate with three uncapped 30-second iperf3 runs per direction, omitting the first five seconds of **each calibration run only**; use the median of the three receiver-side results. Save the calibration summary and both ends' logs. The calibration chosen before the campaign sets fixed rates for that campaign; do not recalibrate a poor session into a pass. If topology or capacity regime materially changes, pause and document a new campaign rather than silently mixing conditions.

A controlled session needs 900 ordered, unique probe slots, no `missed_slot`, no confirmed sleep or >2-second UTC/monotonic discontinuity, and a recorded quality/window report. `timeout` and `ping_process_timeout` remain distinct; they can be included under the 57/60 window rule but must be reported. Sustained receiver-side mean during collector overlap must be within 15% of the declared target, and no complete 60-second overlap block may average below 75% of target. Burst requires all planned pulses to complete with receiver-side summaries and to be fully inside the RTT session; mean receiver-side pulse rate must be within 15% of target, with no pulse below 75% of target. A failing run remains raw evidence, not a controlled session. Do not change rates or labels mid-session.

## Preassigned 32-session plan

Each day has two independent sessions per scenario. Keep the day-level split even if a slot must be repeated; record the failed attempt separately and repeat the same planned slot without reassigning it based on results. Allow the network to settle between runs. The order rotates to reduce scenario/time-of-day confounding. The burst seeds are fixed before collection and are for generation/audit only.

| Collection day | Split | Slots 01–08 in order |
| --- | --- | --- |
| D1 | train | idle, upload, download, burst (seed 101), download, burst (seed 102), idle, upload |
| D2 | train | upload, burst (seed 103), idle, download, burst (seed 104), download, upload, idle |
| D3 | validation | download, idle, burst (seed 105), upload, idle, upload, download, burst (seed 106) |
| D4 | held-out test | burst (seed 107), download, upload, idle, upload, idle, burst (seed 108), download |

This yields four train, two validation, and two held-out test sessions per scenario. Record actual calendar dates and map every `D<day>-<slot>` to its raw `session_id`, load run ID, and server log. Do not inspect D4-derived labels to revise configuration, features, thresholds, or model selection.

## Run procedure

Run commands from the repository root on the newer Wi-Fi Mac, replacing addresses/interface as needed. Before the campaign, verify the route to the old Mac uses the Wi-Fi interface. On the older Ethernet Mac, create a server-log directory and start the server for calibration. A fresh server/log for each loaded session is the default manual procedure:

```sh
mkdir -p netpulse-server-logs
caffeinate -i iperf3 -s -i 1 --logfile "netpulse-server-logs/$(date -u +%Y%m%dT%H%M%SZ)-server.log"
```

The server is **not required for idle**. For an idle slot, stop iperf3 and run `caffeinate -i` by itself on the older Mac to prevent idle system sleep; stop it with Ctrl-C afterward. Stop the server with Ctrl-C after each loaded run and retain its log. Keep the older Mac open and on power; a dark display is acceptable if the system remains awake.

With the server listening, make a new formal calibration and retain the printed summary path:

```sh
bash scripts/mac_mac_iperf3_formal.sh calibrate 192.168.1.151 en0
CALIBRATION_SUMMARY="data/load/calibrate-YYYYMMDDTHHMMSSZ-XXXXXX/summary.json"
```

The following are examples for D1 slots. The wrapper uses the frozen config, checks each slot's assigned scenario and burst seed, records the slot ID in `session.json`, starts the load and collector for loaded modes, and checks burst overlap automatically. Do not start a second collector or iperf3 client.

```sh
bash scripts/mac_mac_iperf3_formal.sh D1-01 idle 192.168.1.151 en0
bash scripts/mac_mac_iperf3_formal.sh D1-02 upload 192.168.1.151 en0 "$CALIBRATION_SUMMARY"
bash scripts/mac_mac_iperf3_formal.sh D1-03 download 192.168.1.151 en0 "$CALIBRATION_SUMMARY"
bash scripts/mac_mac_iperf3_formal.sh D1-04 burst 192.168.1.151 en0 "$CALIBRATION_SUMMARY" 101
```

For other slots, follow the table exactly and substitute their `D<day>-<slot>` ID, scenario, and preassigned burst seed. Check `session.json` for `experiment_id=mac-mac-iperf3-v1`, `experiment_status=frozen`, and the intended slot ID before moving on. Preserve raw probe files, the calibration JSON, client and server iperf3 logs, and burst `run.json`/`events.jsonl`. Do not edit a running script or its config during a session.

For D1, a single interactive script can step through all eight slots **sequentially**. It prints the old Mac's fresh-server command before each loaded slot, waits for you to start it, runs the formal command on the new Mac, then pauses for log review. It cannot start the old Mac's server without separate remote-access setup, and it stops on a failed session command. It does not run scenarios concurrently or silently advance past a failed run. Use the actual new formal calibration path, not a pilot summary:

```sh
bash scripts/collect_formal_day1.sh 192.168.1.151 en0 "$CALIBRATION_SUMMARY" --dry-run
bash scripts/collect_formal_day1.sh 192.168.1.151 en0 "$CALIBRATION_SUMMARY"
```

If you intentionally stop after reviewing a slot, resume from the next unfinished slot with `--from D1-XX`; verify previously completed slots before doing so. Each loaded slot still needs its own old-Mac server log. This D1 convenience script does not replace the per-session quality audit.

### Unattended D1-02 through D1-04 loaded block

Operational addendum, 2026-10-22, before the first formal loaded session: one persistent iperf3 server may serve the preassigned, sequential D1-02 upload, D1-03 download, and D1-04 burst block. This does not alter the frozen measurement values or day-level split. It replaces three separate old-Mac server logs with **one combined server log** for this block; retain the three separate client logs and their retrieved server output. The interactive `collect_formal_day1.sh` above still uses fresh servers and pauses between slots.

After D1-01 idle finishes, start the following on the older Ethernet Mac and leave it running until the block ends. Use `iperf3`, **not** iperf2's `iperf`, and do not add `-1`/`--one-off`:

```sh
mkdir -p netpulse-server-logs
caffeinate -i iperf3 -s -i 1 --logfile "netpulse-server-logs/D1-02-04-$(date -u +%Y%m%dT%H%M%SZ)-server.log"
```

Then on the newer Wi-Fi Mac, substitute the actual formal calibration summary path printed earlier:

```sh
bash scripts/run_formal_d1_loads.sh 192.168.1.151 en0 "data/load/calibrate-YYYYMMDDTHHMMSSZ-XXXXXX/summary.json"
```

Without a restart anchor, this script requires exactly one completed D1-01 and no prior D1-02 through D1-04 attempts. It executes the three assigned modes/seeds in order, waits 60 seconds between modes, keeps the client Mac awake, and writes `data/load/formal-d1-batch-*/batch.log`. It stops on the first command or quick quality-gate failure and never retries or silently changes a rate. The quick gate checks probe completeness/timing, receiver-rate adherence, and burst overlap; complete the full daily audit afterward. Leave both MacBooks open and on power, and allow about 50 minutes.

If D1 is restarted while retaining earlier raw attempts, pass the new completed D1-01 `session_id` as a fourth argument. The batch then checks only D1-02 through D1-04 attempts that start after that idle session ends. Keep the earlier attempts and explicitly exclude them in the final session-to-split manifest; do not delete or relabel them. For example:

```sh
bash scripts/run_formal_d1_loads.sh 192.168.1.151 en0 "$CALIBRATION_SUMMARY" idle-YYYYMMDDTHHMMSSZ-XXXXXXXX
```

## After each day and before modeling

Audit session coverage, clock continuity, RTT distribution, valid and fully observed windows, load adherence, and burst overlap. Document every exclusion with its reason. Complete D1–D4 collection and lock the session-to-split mapping **before** window generation or model fitting. Fit preprocessing on train sessions only, choose models on validation sessions, and evaluate the final selected model once on D4. Compare against the observed-history P95 persistence baseline on identical valid windows, reporting per-session and per-scenario errors and coverage.

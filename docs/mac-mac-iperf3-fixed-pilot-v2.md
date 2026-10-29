# Fixed-rate Wi-Fi RTT pilot v2 (draft)

This is a **trial**, not a frozen formal campaign. It is separate from the capacity-relative [`mac-mac-iperf3-v1`](mac-mac-iperf3-formal-v1.md) sessions. Do not relabel or merge those older sessions into this pilot.

## Question and measurements

Hold the iperf3 sender target constant while the real Wi-Fi path varies. The newer MacBook collects ICMP RTT and runs the iperf3 client over Wi-Fi; the older MacBook answers ICMP over Ethernet and serves iperf3 for loaded modes. A low receiver rate despite an unchanged command is an observed network outcome, not by itself a failed trial. A missing or failed load process is different and must be reported.

The draft config is [`configs/mac-mac-iperf3-fixed-pilot-v2.toml`](../configs/mac-mac-iperf3-fixed-pilot-v2.toml). Trial targets are one TCP stream at 300 Mbit/s for upload, 300 Mbit/s for download (`-R`), and 350 Mbit/s during burst pulses. These are fixed **sender targets**, not promised receiver rates. Calibration is diagnostic context only and does not set these targets. Do not change the targets between trial sessions.

The ICMP collector retains the v1 measurement shape: 900 one-second slots, 56-byte payload, 800 ms reply timeout, no discarded warm-up, and 60 observed slots predicting next-60-slot RTT P95. An observation/label side needs at least 57 successful RTTs. Keep non-`ok` records, including `ping_process_timeout`, with their original status. No scenario label, future pulse plan, or future measured throughput is a model input.

## Trial procedure

Run from the repository root on the newer Wi-Fi Mac. Verify both Macs are on power, VPN is off, the Wi-Fi position/AP/band is recorded, and the route to the older Mac uses `en0`. Keep other deliberate network loads off. Replace the example address/interface as needed. Use `caffeinate -i` on the older Mac to prevent sleep during idle; **do not** run an iperf3 client or server for idle.

```sh
bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh idle 192.168.1.151 en0
```

For each loaded mode, start `caffeinate -i iperf3 -s -i 1 --logfile <unique-server-log>` on the older Mac first. Keep a separate server log for each session, and stop the server when it finishes. The wrapper starts the client load, then the collector, saves the client and retrieved server output, and stops on process failure. Burst seed `42` is an example fixed before the run.

```sh
bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh upload 192.168.1.151 en0
bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh download 192.168.1.151 en0
bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh burst 192.168.1.151 en0 42
```

Run these as **separate** sessions, never concurrently. The script writes `data/raw/<scenario>-.../{session.json,probes.jsonl}` and `data/load/<load_run_id>/...`. The burst load also keeps `run.json`, `events.jsonl`, and one marker-separated `iperf.log`. Preserve raw data and both-end load logs even if a run fails.

## Review before freezing any formal v2 protocol

For each run, inspect 900 unique ordered slots, no `missed_slot`, start lateness, UTC/monotonic continuity, status counts, RTT distribution, and valid/fully observed 60+60 windows. Verify that sustained iperf3 spans the collector and that all burst pulses complete inside it. Record receiver-side per-second or per-pulse rate, TCP retransmissions, and observed rate dips next to RTT spikes. A real rate dip is **not** an automatic exclusion; an interrupted collector, missing pulse, or failed iperf3 process is. Distinguish these before defining formal acceptance rules.

Use this pilot to decide whether 300/350 Mbit/s produces useful contrasts without making the test depend on a one-time capacity estimate. Freeze a separate versioned formal protocol, session plan, and acceptance criteria **before** collecting its train/validation/held-out sessions. Do not promote this pilot into the held-out set.

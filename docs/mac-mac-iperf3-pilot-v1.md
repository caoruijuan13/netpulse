# Two-MacBook iperf3 pilot: Wi-Fi collector, Ethernet responder (draft)

This is the current two-MacBook trial topology. The newer development MacBook runs the collector and iperf3 client over **Wi-Fi**; the 2015 Intel MacBook answers ICMP Echo and runs the iperf3 server over **Ethernet**. Use [mac-mac-iperf3-pilot-v1.toml](../configs/mac-mac-iperf3-pilot-v1.toml) for new runs. The earlier [Ethernet-collector/Wi-Fi-server draft](mac-mac-iperf3-pilot.md) and Windows/iperf2 M0-v1 remain historical. Do not mix their windows with this topology in one controlled dataset.

## Idle trial sessions already collected

The `idle-20261022T033416Z-520675fd` session recorded the intended physical direction in its metadata: Wi-Fi source `en0`, Ethernet target. It used the earlier draft config hash with explicit command-line link overrides. All 900/900 ordered probe slots are `ok`; the run completed, start lateness never exceeded 13.6 ms, and no wall-clock/monotonic discontinuity was found. All 73 candidate windows pass the provisional 57/60 probe-availability rule. The user confirmed that no iperf3 client ran during this 900-second run; only `iperf3 -s` was open on the target. It is an exploratory idle session.

RTT median is 4.807 ms, P95 is 76.028 ms, maximum is 228.001 ms, and 111/900 replies exceed 50 ms. After excluding the first 60-second warm-up, P95 is still 74.164 ms; high RTTs occur throughout the run. Keep the observed idle tail and investigate or repeat before freezing a controlled low-latency reference.

The all-Ethernet `idle-20261022T042905Z-ce6683b4` session also had 900/900 successful probes, with RTT median 1.957 ms and P95 2.156 ms; the user likewise confirmed no iperf3 client ran during it. The previously associated 882 and 571 Mbit/s figures cannot be throughput produced by these idle sessions, because a listening `iperf3 -s` has no transfer to measure without a client. Their measurement runs remain unidentified, so they are kept only as unverified topology context in [`data/annotations/throughput-context-2026-10-22.json`](../data/annotations/throughput-context-2026-10-22.json), not as per-session load or model features. The RTT comparison is between two idle topologies; one pair of runs alone does not establish the cause of the Wi-Fi-path tail.

A second Wi-Fi-to-Ethernet idle session, `idle-20261022T050841Z-feaeba88`, ran with the iperf3 server closed. It also has 900/900 successful probes and no detected clock jump. Its RTT median is 4.742 ms, P95 is 64.768 ms, and 70/900 replies exceed 50 ms; the long tail remains present across all three five-minute blocks. Closing the server did not eliminate the tail. The two Wi-Fi sessions are not a controlled A/B proof of the server process's effect, but they are both valid exploratory idle observations.

## Fixed roles and scenarios

Keep both Macs on power and awake. Record the new Mac's Wi-Fi interface/address, the old Mac's Ethernet address, macOS and iperf3 versions, Wi-Fi band/channel and location, router/AP, VPN, and background traffic. Target the old Mac's **Ethernet IPv4 address**. If either Mac has both Wi-Fi and Ethernet active, confirm that the collector and iperf3 traffic use the intended path; do not infer the path from the address label alone. Limit ICMP and iperf3's TCP port (default 5201) to the private experiment network.

The current draft has **no discarded warm-up period** in any scenario (`warmup_seconds = 0`). The first 60 probes still form the earliest observation window, so the first prediction of a following 60-second window is only possible after those 60 probes. A complete 900-probe session has 79 candidate history/future pairs at a 10-slot stride, subject to quality checks. Earlier trial sessions retain their recorded 60-second warm-up metadata; do not rewrite them. The burst generator's 30-second initial delay is only a startup-alignment buffer, not an exclusion of early RTT data. The calibration command's `-O 5` likewise omits only the first five seconds of each separate capacity test, not of an RTT scenario session.

`upload` and `download` are named from the **new collector MacBook's perspective**:

| Scenario | Generated TCP direction | iperf3 client on new Wi-Fi Mac |
| --- | --- | --- |
| `idle` | None | No iperf3 client |
| `upload` | Wi-Fi → Ethernet | One normal stream |
| `download` | Ethernet → Wi-Fi | One reverse (`-R`) stream |
| `burst` | Wi-Fi → Ethernet | One stream per randomized 10–20 s pulse, with 20–40 s gaps |

The old 75 Mbit/s normal and 250–300 Mbit/s reverse figures were reported for the **opposite device/link assignment**; they are not capacities or targets for this configuration. Single-stream profiles remain a provisional simplification. Do not change flow count within a session. Keep ICMP at 1 Hz with a 56-byte payload and 800 ms timeout; apply the provisional 60-second history/future windows and 57/60 successful-reply rule only after the pilot quality review. The new topology is not frozen for formal collection.

## Idle and directional calibration

On the Wi-Fi development Mac, run the idle collector from the repository root. Replace the address and interface if needed. For `idle`, stop the iperf3 client and any other experiment load. The Ethernet Mac only needs to be awake and answer ICMP Echo; `iperf3 -s` is not required. Leaving the server listening, as in the two already-collected sessions, does not itself create transfer traffic.

```sh
PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
  --config configs/mac-mac-iperf3-pilot-v1.toml \
  --target <OLD_MAC_ETHERNET_IP> --scenario idle \
  --source-interface <NEW_MAC_WIFI_IFACE> \
  --source-link wifi --target-link ethernet \
  --environment-notes "Both MacBooks on power; fixed Wi-Fi position; VPN off"
```

Before loaded scenarios, run three uncapped one-stream iperf3 trials in **each** direction. Each uses a five-second omitted pre-test (`-O 5`) followed by 30 measured seconds (`-t 30`). Use each JSON result's receiver-side `end.sum_received.bits_per_second`, then take the median of the three trial rates as that direction's capacity. The sustained target is 70% of the matching direction's capacity; burst uses 90% of the Wi-Fi→Ethernet capacity. Do not use the previously reported 571/882 Mbit/s figures as calibration for these runs: their measurement source is not verified.

On the old Ethernet Mac, start the server on the default TCP port 5201 with a fresh log for calibration, then restart it with a fresh log for each loaded scenario. The calibration/upload/download helper uses this default port. The server needs to keep running across the burst pulses. Stop it after each run with Ctrl-C:

```sh
mkdir -p netpulse-server-logs
iperf3 -s -i 1 --logfile "netpulse-server-logs/$(date -u +%Y%m%dT%H%M%SZ)-server.log"
```

On the new Wi-Fi Mac, verify the old Mac's current Ethernet IPv4 address (`192.168.1.151` in the reviewed sessions) and the new Mac's Wi-Fi interface (`en0` in those sessions). Then run the calibration script from the repository root while the server is listening:

```sh
bash scripts/mac_mac_iperf3_trial.sh calibrate 192.168.1.151 en0
```

The script writes six iperf3 JSON logs plus `summary.json` under an ignored `data/load/calibrate-.../` directory. Its `directions.upload.capacity_mbps` and `directions.download.capacity_mbps` values come from the matching receiver-side trial results. A failed trial stops calibration; do not substitute a previously reported topology rate. Save the old Mac's server log alongside the client-side calibration directory when reviewing the result. Copy the printed `summary.json` path into `CALIBRATION_SUMMARY` below.

## Loaded pilot sessions

Run one 15-minute collector session each for `upload`, `download`, and `burst`, separate from idle. For sustained scenarios, the script starts a 930-second iperf3 client, waits three seconds, then starts the 900-second collector and records the load run ID, direction, and target in `session.json`. It saves the client/server-retrieved iperf output under ignored `data/load/<load_run_id>/iperf.log`. Keep a separate server log on the old Mac. `-b` is **per stream**; with this one-stream profile it equals the aggregate target. A requested bitrate alone does not establish delivered load. Do not use `--bidir` as a shortcut for two separate scenarios: it creates simultaneous bidirectional traffic and would need its own calibration and scenario definition. See the [iperf3 manual](https://software.es.net/iperf/invoking.html).

```sh
# Replace this with the actual path printed by the calibration script.
CALIBRATION_SUMMARY="data/load/calibrate-YYYYMMDDTHHMMSSZ-XXXXXX/summary.json"
# Run separately, restarting the server with a fresh log between scenarios.
bash scripts/mac_mac_iperf3_trial.sh upload 192.168.1.151 en0 "$CALIBRATION_SUMMARY"
bash scripts/mac_mac_iperf3_trial.sh download 192.168.1.151 en0 "$CALIBRATION_SUMMARY"
```

For `upload` and `download`, the wrapper starts both processes; do not start a second client or collector manually. Confirm in the client log that the iperf3 command completed normally and inspect the receiver-side rate. The collector itself still measures ICMP RTT independently of iperf3.

For `burst`, restart the old Ethernet Mac's iperf3 server with a fresh log, then run one command on the new Wi-Fi Mac. The wrapper checks that the route uses `en0`, starts the existing burst generator, reads its printed run ID, and starts the 900-second collector during the generator's initial 30-second delay:

```sh
CALIBRATION_SUMMARY="data/load/calibrate-YYYYMMDDTHHMMSSZ-XXXXXX/summary.json"
bash scripts/mac_mac_iperf3_trial.sh burst 192.168.1.151 en0 "$CALIBRATION_SUMMARY" 42
```

The generator uses 90% of the upload capacity and records the seed (`42` above). It writes `run.json`, `events.jsonl`, and a single marker-separated `iperf.log` in ignored `data/load/<burst_run_id>/`; the wrapper puts that ID in the collector's `session.json` and saves its own launch log. Do not start a second collector. The burst plan is limited to the collector's 900-second duration, and the wrapper checks after completion that every successful pulse was fully inside the matching RTT session. A failed overlap check means the pair is not a complete controlled burst run, even if both processes exited normally. Keep the server's separate log and check receiver-side pulse rates. This wrapper assumes TCP port 5201. Do not expose future pulse timings to the model.

## Pilot review

Check ordered slot coverage, status counts, RTT median/P95/max, scheduling offsets, clock/sleep discontinuities, accepted and fully observed windows, actual receiver-side load, and load overlap. The provisional sustained-load adherence check is a receiver-side mean within 15% of the predeclared target during collector overlap, with no complete 60-second overlap block below 75% of target. Keep failed runs as raw evidence; do not retarget mid-session. Repeat or investigate the Wi-Fi-path idle RTT tail before using it as a controlled low-latency reference. Freeze a separate formal protocol only after reviewing all four scenarios and the saved calibration evidence; assign train/validation/test by whole session afterward.

# Two-MacBook iperf3 pilot (draft)

Historical first draft: Ethernet collector / Wi-Fi server. The current trial uses the **opposite** links; see [the Wi-Fi-collector / Ethernet-server pilot](mac-mac-iperf3-pilot-v1.md). The commands below are not the current procedure.

This is a **new pilot**, not a revision of the completed Windows/iperf2 M0-v1 pilot. The old configuration, raw sessions, and conclusions remain historical. Use [mac-mac-iperf3-pilot.toml](../configs/mac-mac-iperf3-pilot.toml) for new sessions; do not pool old and new windows as one controlled dataset. No completed two-MacBook session or independently verified achieved rate is claimed here yet.

## Fixed setup and scenarios

The development MacBook stays on Ethernet and runs the ICMP collector plus the iperf3 client. The 2015 Intel MacBook stays on Wi-Fi at a fixed position, answers ICMP Echo, and runs the iperf3 server. Keep both awake and on power; note the macOS and iperf3 versions, Wi-Fi band/channel, router/AP, interfaces, VPN state, and any changes. Use the Wi-Fi MacBook's local IPv4 address as the collector and iperf3 target. Keep the path on the private experiment network; allow only the necessary ICMP and iperf3 TCP port (default 5201) there. Do not run another load test while a session is being collected.

| Scenario | Traffic direction | iperf3 profile |
| --- | --- | --- |
| `idle` | None | Server may be idle; no test client |
| `upload` | Ethernet MacBook → Wi-Fi MacBook | One sustained TCP stream |
| `download` | Wi-Fi MacBook → Ethernet MacBook | One sustained TCP stream using `-R` |
| `burst` | Ethernet MacBook → Wi-Fi MacBook | One TCP stream per pulse; randomized 10–20 s on / 20–40 s off |

Single-stream download is intentional: the old four-stream workaround was chosen for the Windows sender and is not inherited. If the new path proves unreliable at one stream, retain those observations and design a separately named/versioned multi-stream profile rather than silently switching `download` to `-P 4`. The ICMP payload, 1 Hz cadence, 800 ms timeout, 60/60-second windows, and 57/60 rule are initially copied from M0-v1 to isolate the topology/tool change. They remain **draft** until this pilot is reviewed; the new topology does not inherit M0-v1's frozen status.

The initial short-test report with the Wi-Fi MacBook as `-s` and the Ethernet MacBook as `-c` is approximately **75 Mbit/s for ordinary `-c` (Ethernet → Wi-Fi)** and **250–300 Mbit/s for `-R` (Wi-Fi → Ethernet)**. One and four streams reportedly gave similar throughput in each direction. This supports the one-stream design, but the rounded figures are not yet an auditable three-trial, receiver-side capacity estimate. Preserve the exact logs and per-trial values before freezing target rates. Do not infer symmetry or copy one direction's rate to the other.

## Use the completed short calibrations

For each direction, retain three separate 30-second uncapped, **one-stream** iperf3 trials and both ends' logs. `-O 5` omits startup seconds from the reported statistics. Calculate each trial's median receiver-side per-second throughput after startup, then the median of the three trial medians. Call these `upload_capacity_mbps` and `download_capacity_mbps`. If the completed short calibration used fewer repetitions or a different flow count, treat it as provisional and repeat the missing trials before declaring a controlled load. Do not copy the Windows pilot's 310 Mbit/s capacity or 217 Mbit/s target.

On the Wi-Fi MacBook, start a server in its own terminal, saving its output to a new file with an existing parent directory. Restart it with a fresh log for each separate trial or session:

```sh
iperf3 -s -i 1 --logfile <WIFI_SERVER_LOG>
```

On the Ethernet MacBook, the calibration commands are:

```sh
iperf3 -c <WIFI_MAC_IP> -t 30 -O 5 -P 1 -i 1 --get-server-output --logfile <UPLOAD_TRIAL_LOG>
iperf3 -c <WIFI_MAC_IP> -t 30 -O 5 -R -P 1 -i 1 --get-server-output --logfile <DOWNLOAD_TRIAL_LOG>
```

The target sustained bitrate is `round(0.70 × matching_direction_capacity_mbps × 1,000,000)` bits/s. The burst target is `round(0.90 × upload_capacity_mbps × 1,000,000)` bits/s. For this one-stream profile, each `-b` value equals the aggregate target. `-b` is a request, not proof that the receiver got that rate. If a future profile uses `-P 4`, iperf3 applies `-b` to **each stream**; divide the aggregate target by four and verify the receiver's aggregate. [iperf3's manual](https://software.es.net/iperf/invoking.html) defines `-R`, `-P`, `-b`, `--logfile`, and `--get-server-output`.

As a **pilot-only starting point from the rounded report**, 70% of 75 Mbit/s is 52.5 Mbit/s for upload. The reported reverse range does not yield one defensible 70%-of-capacity number; 175 Mbit/s is 70% of its lower observed 250 Mbit/s, a conservative trial setting rather than a frozen download target. The corresponding provisional burst target from 75 Mbit/s would be 67.5 Mbit/s. Replace these with values derived from the saved three-trial receiver logs, and record any change as a new run rather than changing load mid-session.

## One pilot session per scenario

Run `idle`, `upload`, `download`, and `burst` as separate 15-minute collector sessions. Start a sustained iperf3 load with `-t 930`, then start the collector promptly; save actual load start/end times and check that the load spans all 900 collector seconds. Use a fresh client log and a fresh Wi-Fi server log for every session. iperf3's client output identifies both sender and receiver summaries; `--get-server-output` also captures server output when the test completes. Preserve the separate server log even if the client is interrupted. Review receiver-side one-second rates during the collector overlap, not only the end summary.

```sh
# Ethernet MacBook: upload load
iperf3 -c <WIFI_MAC_IP> -t 930 -b <UPLOAD_TARGET_BPS> -P 1 -i 1 --get-server-output --logfile <UPLOAD_CLIENT_LOG>

# Ethernet MacBook: download load (Wi-Fi MacBook sends)
iperf3 -c <WIFI_MAC_IP> -t 930 -R -b <DOWNLOAD_TARGET_BPS> -P 1 -i 1 --get-server-output --logfile <DOWNLOAD_CLIENT_LOG>
```

In another Ethernet-MacBook terminal, start the collector for the selected scenario. Replace the interface and address; for `idle`, omit `--traffic-tool` and `--traffic-settings-json` entirely. For load scenarios, record the actual capacity trial references, tool versions, command, one-stream target, and load-run ID in the JSON metadata (example below). The collector records these settings but does **not** start iperf3.

```sh
PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
  --config configs/mac-mac-iperf3-pilot.toml \
  --target <WIFI_MAC_IP> --scenario upload \
  --source-interface <ETHERNET_IFACE> --source-link ethernet --target-link wifi \
  --traffic-tool iperf3 \
  --traffic-settings-json '{"direction":"ethernet_to_wifi","parallel_streams":1,"target_rate_bps":<UPLOAD_TARGET_BPS>,"load_run_id":"<RUN_ID>","client_command":"<EXACT_COMMAND>","calibration_reference":"<TRIAL_IDS>"}' \
  --environment-notes "Two MacBooks on power; fixed Wi-Fi position; VPN off"
```

The angle-bracket tokens in the JSON example must be replaced with valid JSON values before running. For `download`, set `--scenario download`, `direction` to `wifi_to_ethernet`, and record `reverse: true`. For `burst`, use `direction: ethernet_to_wifi` and the burst generator's printed run ID. Do not treat the load direction as the ICMP probe direction: ICMP always originates on the Ethernet MacBook.

### Burst generator

Keep the iperf3 server running on the Wi-Fi MacBook with its own log. On the Ethernet MacBook, run:

```sh
PYTHONPATH=src python3 -m netpulse.burst \
  --config configs/mac-mac-iperf3-pilot.toml \
  --target <WIFI_MAC_IP> \
  --capacity-mbps <MEASURED_ONE_STREAM_UPLOAD_CAPACITY> \
  --seed <RECORDED_INTEGER_SEED>
```

The generator prints a `burst-<UTC_TIMESTAMP>-<SUFFIX>` ID. It saves `run.json`, `events.jsonl`, and one marker-separated `iperf.log` under ignored `data/load/<run_id>/`. Each pulse uses iperf3 `-b` with one stream and requests server output. Start the burst collector during the generator's initial 30-second delay, recording that ID as `load_run_id`. Save the Wi-Fi server log alongside the run evidence; the client log alone is insufficient if a pulse or connection fails. Check actual pulse times and receiver rates, and do not supply future pulse timing to the prediction model.

If port 5201 is unavailable, start the server with `-p <PORT>` and pass the same `--port <PORT>` to the burst generator; record that port in the collector's traffic settings.

## Review and decision

For every run, inspect slot completeness, probe statuses, RTT median/P95/max, scheduling offsets, wall-clock discontinuities, window coverage, achieved receiver throughput, and load overlap. Apply the existing 57/60 window rule provisionally; retain failures as raw evidence. A sustained pilot session meets the provisional load-adherence check only when receiver-side mean during collector overlap is within 15% of its predeclared target and no complete 60-second overlap block averages below 75% of target. A confirmed sleep invalidates a controlled session. Do not adjust the target mid-session to obtain a pass.

After the four pilot sessions, decide whether to freeze this profile for formal M1 collection. Record the actual capacities, rates, device versions, and any exclusions first. Keep training/validation/test split by complete **new** session; historical Windows/iperf2 pilot data are not part of the new final test.

## Historical command used for the all-Ethernet idle trial

The following collector command was used with explicit link overrides for the 2026-10-22 all-Ethernet idle run. The user confirmed that no iperf3 client ran; only `iperf3 -s` was open on the target. Its config describes the opposite topology, so use [the new v1 config and procedure](mac-mac-iperf3-pilot-v1.md) for future runs.

idle:
```sh
PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
  --config configs/mac-mac-iperf3-pilot.toml \
  --target 192.168.1.151 \
  --scenario idle \
  --source-interface en0 \
  --source-link wifi \
  --target-link ethernet \
  --environment-notes "Both MacBooks on power; all ethernet; VPN off"
```

upload:
```sh
PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
  --config configs/mac-mac-iperf3-pilot.toml \
  --target 192.168.1.151 \
  --scenario upload \
  --source-interface en0 \
  --source-link wifi \
  --target-link ethernet \
  --environment-notes "Both MacBooks on power; all ethernet; VPN off"
```

download:
```sh
PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
  --config configs/mac-mac-iperf3-pilot.toml \
  --target 192.168.1.151 \
  --scenario download \
  --source-interface en0 \
  --source-link wifi \
  --target-link ethernet \
  --environment-notes "Both MacBooks on power; all ethernet; VPN off"
```

burst:
```sh
PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
  --config configs/mac-mac-iperf3-pilot.toml \
  --target 192.168.1.151 \
  --scenario burst \
  --source-interface en0 \
  --source-link wifi \
  --target-link ethernet \
  --environment-notes "Both MacBooks on power; all ethernet; VPN off"
```
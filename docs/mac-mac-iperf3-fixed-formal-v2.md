# Two-MacBook fixed-load formal v2

Frozen before D1-01: newer MacBook on Wi-Fi (`en0`) collects ICMP and runs the
iperf3 client; older MacBook on Ethernet (`192.168.1.151`) answers ICMP and
listens with iperf3 for loaded scenarios. Both remain on power and awake, in a
fixed position/AP/band, with VPN off. Keep any deviation in the session record.
This experiment is `mac-mac-iperf3-fixed-v2`; do not relabel or merge the old
capacity-relative v1 or either draft fixed-rate pilot into it.

The one-stream sender targets are fixed at **360 Mbps upload**, **300 Mbps
download** (`iperf3 -R`), and **460 Mbps Wi-Fi-to-Ethernet burst**. Idle has no
client load; an iperf3 server merely listening is allowed. Do not recalibrate
these targets during this campaign. Preserve both-end iperf3 output. Measured
receiver-rate dips and TCP retransmissions are outcomes to record, not automatic
exclusions. A missing/failed load process or incomplete burst pulse is different.

Each session has 900 one-second ICMP slots, 56-byte payload, 800 ms timeout,
no discarded warm-up, and 60 observed slots predicting the next 60-slot RTT
P95 with stride 10. A window is valid with at least 57 successful RTTs on each
side. Keep every original non-`ok` status. Accept a controlled session only
with 900 ordered unique slots, no `missed_slot`, no confirmed sleep or major
UTC/monotonic discontinuity, and a completed, correctly overlapping load for
non-idle scenarios. Report all rate dips, retransmissions, and rejected windows;
do not silently replace a failed attempt.

Use the existing preassigned 32-slot order and burst seeds from
[`check_formal_slot.py`](../scripts/check_formal_slot.py): D1/D2 train, D3
validation, D4 held-out. D1-01 through D1-04 are idle, upload, download,
burst (seed 101). Each formal slot is identified by both this v2 experiment ID
and `slot_id=D1-XX` in `session.json` environment notes; the batch log maps
slots to session IDs. The pilot sessions are never held-out test data. Freeze
the session-to-split mapping before generating model windows or fitting models.

With the old Mac's persistent `caffeinate -i iperf3 -s` already running, launch
the first four slots from the newer Mac:

```sh
bash scripts/run_fixed_formal_v2_d1_01_04.sh 192.168.1.151 en0
```

The script runs the four slots sequentially, waits 60 seconds between them,
stops on the first command failure, and writes a batch log under `data/load`.
Leave the server running through the loaded block and retain its server log.

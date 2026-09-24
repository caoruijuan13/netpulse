# M0 pilot observations — 2026-09-24

Status: **M0 pilot reviewed and M0-v1 frozen**. The user reports that the MacBook used Ethernet and the Windows PC used Wi-Fi. Session metadata records `source_link=ethernet` and `target_link=wifi`, consistent with that report; the collector does not independently verify the physical links. Raw session files remain unchanged. This document distinguishes the initial failed/limited runs from the later repeats used to choose the frozen protocol.

## Initial four-scenario review

| Session | Probe results (900 slots each) | Valid candidate windows | Interpretation |
| --- | --- | --- | --- |
| idle (`20260924T023745Z-a5805ed6`) | 900 ok | 73/73 | Clean exploratory reference. |
| upload (`20260924T035559Z-95903725`) | 880 ok, 10 `send_error`, 10 `missed_slot` | 21/73 | Too few valid windows for a robust scenario comparison; diagnose and repeat. |
| download (`20260924T041910Z-d6a70f54`) | 900 ok | 67/73 after clock-gap exclusion | Probe outcomes are complete, but a clock discontinuity needs investigation. |
| burst (`20260924T045236Z-a2a02e93`) | 880 ok, 10 `send_error`, 10 `missed_slot` | 25/73 | Generator finished, but probe quality under pulses needs investigation and a repeat. |

All four sessions report `run_status=completed` and contiguous probe sequence numbers. Candidate windows are counted at decision slots 119, 129, …, 839, with a 60-slot history, 60-slot forecast, and first 60 slots excluded as warm-up. A candidate is invalid if either window contains `send_error` or `missed_slot`; six download candidates also cross the clock discontinuity. These counts describe data availability, not prediction accuracy.

In upload and burst, each of the ten `ping_process_timeout` errors is followed by a `missed_slot`, yielding ten two-slot error pairs per session. These are collector/process outcomes, not measured ICMP packet losses. All ten burst errors occurred during active load pulses. The download run has a 65.889-second UTC interval between slots 846 and 847 while the corresponding monotonic interval is 1.164 seconds. The Mac power log later confirmed an idle sleep from 12:33:15 to 12:34:22 local time. The session spans about 965 seconds in UTC although the monotonic probe schedule spans 900 seconds. Exclude derived windows crossing that sleep interval.

The upload metadata specifies Mac → PC with a 217 Mbit/s target; download specifies PC → Mac with a 189 Mbit/s target. No independent iperf2 output for these sustained sessions was found in the repository, so their achieved throughput and actual traffic direction cannot be verified from the saved evidence. The burst metadata links to `data/load/20260924T045229Z-0346d17e/`: its generator run completed 20 of 20 planned pulses at a 279 Mbit/s target. Nineteen pulses overlap the collector session; the last starts after collection ends. Pulse logs exist, but the target rate alone is not proof of uniform achieved load.

## Initial decision and follow-up checks

At this initial review, M0 exit criteria were not yet met. Upload/burst window coverage, sleep prevention and exclusion, and independent generator logs needed follow-up. The inspected sessions were pilot data, not an untouched held-out test set or evidence of model accuracy.

## Repeat upload and burst: window-rule sensitivity analysis

The later upload session (`upload-20260924T070640Z-5df4254a`, collector `m0-pilot-2`) and burst session (`burst-20260924T072950Z-0ed6b65d`, collector `m0-pilot-3`) each wrote 900 contiguous slots with no `missed_slot` and no detected sleep/time discontinuity. Upload had 21 `ping_process_timeout` records and burst had 11. The burst generator completed 20 pulses, 19 of which overlapped collection. Sender-side iperf logs exist for both; PC receiver-side throughput remains unverified.

| Session | Original rule: no `send_error` | Draft rule: allow up to 3 `ping_process_timeout` per 60-slot window | Maximum such errors in one 60-slot window |
| --- | ---: | ---: | ---: |
| Repeat upload | 3/73 valid | 73/73 valid | 3 |
| Repeat burst | 3/73 valid | 73/73 valid | 2 |

The reviewed rule keeps the 57/60 successful-probe minimum separately for history and future windows and still rejects `missed_slot` or any other `send_error`. It treats `ping_process_timeout` as a missing observation of unknown cause, **not** as confirmed network packet loss. The jump from 3/73 to 73/73 is a retrospective sensitivity result on inspected pilot data, not an independently validated improvement. Report the fully observed fraction (3/73 for both), process-timeout rate, and RTT error together; future errors and the burst schedule must never be model inputs.

## Later download repeats and M0-v1 closure

All rows below are exploratory pilot sessions, not formal train/validation/test sessions. Counts use the frozen 57/60 rule on 73 candidate decision slots per 900-slot session. No repeat below has a `missed_slot` or a detected wall-clock-versus-monotonic discontinuity greater than two seconds between adjacent started probes. RTT P95 values describe successful probes over the full session, not model prediction error.

| Scenario/session | Probe outcomes | Valid / fully observed windows | Successful RTT P95 | Load evidence and interpretation |
| --- | --- | --- | ---: | --- |
| idle (`20260924T023745Z-a5805ed6`) | 900 `ok` | 73/73 / 73/73 | 5.368 ms | Clean reference; no generated load. |
| upload (`upload-20260924T070640Z-5df4254a`) | 879 `ok`, 21 `ping_process_timeout` | 73/73 / 3/73 | 12.714 ms | Mac sender log reports 217 Mbit/s over 930 seconds; PC receiver log was not retained. |
| download, default single flow (`download-20260924T085429Z-2ffbdfa5`) | 900 `ok` | 73/73 / 73/73 | 5.242 ms | Mac receiver log reports 39.6 Mbit/s; not a 70%-of-four-flow-capacity test. |
| download, four flows with mistaken per-flow 217M target (`download-20260924T091745Z-98120d8b`) | 899 `ok`, 1 `ping_process_timeout` | 73/73 / 61/73 | 22.477 ms | Mac receiver `[SUM]` reports 309 Mbit/s; near capacity, not 217 Mbit/s aggregate. |
| download, four flows with 54.25M target per flow (`download-20260924T094218Z-7d854a29`) | 899 `ok`, 1 `ping_process_timeout` | 73/73 / 61/73 | 14.960 ms | Mac receiver `[SUM]` reports 217 Mbit/s over 930 seconds, matching the declared 70%-of-310M aggregate target. The Windows client command is recorded in session metadata; its output file is not in this repository. |
| burst (`burst-20260924T072950Z-0ed6b65d`) | 889 `ok`, 11 `ping_process_timeout` | 73/73 / 3/73 | 12.100 ms | Generator completed 20 pulses; 19 overlapped collection. Mac sender log exists; PC receiver log was not retained. |

The default single-flow PC-to-Mac throughput fell to roughly 40–60 Mbit/s despite a prior roughly 300 Mbit/s single-flow observation reported by the user. A short `-P 4` test reached about 310 Mbit/s, and a single-flow `-w 256K` test reached about 120 Mbit/s. The cause of this change is unverified; the pilot does not establish a Windows or Wi-Fi root cause. The three download profiles therefore remain separate and are not pooled as if they were identical conditions.

M0-v1 freezes one Mac-to-PC flow for sustained upload, four PC-to-Mac flows for sustained download, and one Mac-to-PC flow per burst pulse. Four-flow iperf2 pacing is per flow: a 217 Mbit/s aggregate target was achieved in the repeat by requesting 54.25 Mbit/s per flow and checking the receiver `[SUM]`. The corrected download's 217 Mbit/s and 14.960 ms RTT P95 differ from the idle reference's 5.368 ms P95, without treating this pilot contrast as predictive performance. The 57/60 missing-RTT rule, sleep/time exclusion, achieved-load gate, and session-level split are frozen in [experiment-spec.md](experiment-spec.md) and [m0-v1.toml](../configs/m0-v1.toml). Historical pilot sessions are excluded from the untouched final test. Missing receiver-side logs on upload/burst limit historical load claims and become a required M1 collection check rather than a reason to rewrite raw pilot data.

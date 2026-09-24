# M0 raw data contract

Status: **M0-v1 frozen on 2026-09-24** for new controlled sessions. The collector's schema remains version 1. Inspected exploratory sessions retain their original files and metadata; their quality review is in [pilot-observations.md](pilot-observations.md). Any later change to field meaning requires a new protocol/schema version rather than reinterpreting old records.

## Files and identity

Each session produces one metadata JSON file and one UTF-8 probe JSON Lines file under a local, ignored `data/raw/<session_id>/` directory. New session IDs begin with the scenario, for example `upload-<UTC_TIMESTAMP>-<SUFFIX>`; older pilot IDs are left unchanged. The files remain named `session.json` and `probes.jsonl` inside that directory. A session ID is unique and stable across its two files. The metadata file is created at session start and finalized at session end; raw probe records are append-only. Processing creates separate derived files. Do not commit local addresses, SSIDs, or raw measurements without review.

### `session.json`

Required fields:

| Field | Type | Definition |
| --- | --- | --- |
| `schema_version` | integer | Start at `1`; change when field meanings change |
| `session_id` | string | Unique ID, also used in the path and probe records |
| `scenario` | enum | `idle`, `upload`, `download`, or `burst` |
| `started_at_utc`, `ended_at_utc` | ISO 8601 UTC strings | Session boundaries; end is written when collection stops |
| `run_status` | enum | `running`, `completed`, `interrupted`, or `failed` |
| `collector_version` | string | Source version or commit ID for reproducibility |
| `collector_source_sha256`, `config_source_sha256` | strings | Hashes of the collector source and pilot configuration used |
| `source_os`, `source_interface` | strings | MacBook OS and network interface |
| `source_link`, `target_link` | strings | Expected `ethernet` and `wifi`; record actual values |
| `target_address` | string | PC address used for this session |
| `probe_protocol`, `probe_payload_bytes`, `probe_interval_seconds`, `probe_timeout_ms` | string/numbers | Exact probe settings used |
| `history_samples`, `future_samples`, `window_stride_samples`, `minimum_successful_probes`, `target_percentile`, `percentile_method` | integers/string | Label/window settings in force for the session; labels are still derived offline |
| `traffic_tool`, `traffic_settings` | string/object or null | Load generator and settings; null for idle |
| `environment_notes` | string | AP, location, power/VPN state, interruptions, or other relevant changes |
| `expected_probe_slots`, `recorded_probe_slots`, `probe_counts` | integers/object | Planned and written slot counts; counts by status |

`ended_at_utc` may be null only while collection is active. An interrupted or crashed session remains identifiable and is marked incomplete during validation. Session metadata records the *planned* load; measured throughput requires separate sender and receiver iperf logs and must not be inferred from the scenario label. For new controlled load sessions, `traffic_settings` must identify direction, iperf version, exact client command, flow count, aggregate target, per-flow target where applicable, capacity calibration reference, and load run ID. The log paths, actual load start/end UTC times, and measured receiver-side aggregate throughput are linked in an external load-evidence manifest keyed by `session_id`; they are not invented as raw collector fields.

### `probes.jsonl`

Exactly one record per scheduled probe slot, including timeouts and collector failures:

| Field | Type | Definition |
| --- | --- | --- |
| `schema_version` | integer | Same version as session metadata |
| `session_id` | string | Must match `session.json` |
| `probe_seq` | nonnegative integer | Contiguous, zero-based slot number |
| `started_at_utc` | ISO 8601 UTC string or null | Actual probe start time; null if no probe started |
| `scheduled_monotonic_ns` | integer | Planned slot time on the collector's monotonic clock |
| `started_monotonic_ns` | integer or null | Actual start on the same clock; null for a missed slot |
| `status` | enum | `ok`, `timeout`, `send_error`, or `missed_slot` |
| `rtt_ms` | nonnegative number or null | RTT reported by the probe only when `status=ok` |
| `error_code` | string or null | Diagnostic code for a non-`ok` outcome |
| `diagnostic` | string, optional | Bounded original probe output or error text for a non-`ok` result |

The collector must retain the slot record even if the request fails. `rtt_ms` is null for every non-`ok` status. `scheduled_monotonic_ns` and `started_monotonic_ns` are used to check local scheduling delay; monotonic values are meaningful only within the same machine run. UTC timestamps are for identification and cross-session ordering, not sub-millisecond RTT calculation. `diagnostic` preserves bounded original output when a probe fails so that a `send_error` can be audited. An interrupted session may end before all planned slots are written; `run_status` and the two slot counts identify that case.

## Derived examples

Create windows only after validating the raw session. For decision slot `t`, inputs use slots `t-59..t` and the target uses `t+1..t+60`. Exclude the first `warmup_seconds / probe_interval_seconds` slots from every observation window. Do not build a window across session boundaries, a change in probe configuration, or a sleep/time discontinuity. The label is the nearest-rank 95th percentile of successful RTTs in the future window when the frozen validity rules in [experiment-spec.md](experiment-spec.md) pass. Retain the original status and error code for each missing RTT; do not relabel `ping_process_timeout` as packet loss. Keep counts of candidate, accepted, rejected, and fully observed windows, with rejection reasons and separate error rates. A load-adherence failure is a session-level eligibility decision and never changes raw probe outcomes.

Derived data records must carry `session_id`, `decision_probe_seq`, `split`, target value or null, and validity/rejection reason. Split assignment is a separate versioned manifest keyed by `session_id`; it must not be inferred from window row order.

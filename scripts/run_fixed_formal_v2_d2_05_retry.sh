#!/usr/bin/env bash
# Retry only D2-05; preserve the failed first attempt and do not advance D2-06.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo 'Usage: bash scripts/run_fixed_formal_v2_d2_05_retry.sh <SERVER_IP> <WIFI_IFACE>' >&2
  exit 2
fi
server_ip=$1
wifi_iface=$2
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
export NETPULSE_FIXED_CONFIG="$repo_dir/configs/mac-mac-iperf3-fixed-v2.toml"
export NETPULSE_FIXED_RUN_TAG=formal-v2-d2c
export NETPULSE_SLOT_ID=D2-05

python3 - <<'PY'
import json
from pathlib import Path

selection = json.loads(Path('data/load/fixed-formal-v2-d2-01-04-20261025T014235Z-LFQUfP/selection.json').read_text())
if selection.get('experiment_id') != 'mac-mac-iperf3-fixed-v2' or selection.get('status') != 'accepted_after_audit':
    raise SystemExit('D2-01..04 selection is not accepted')
if set(selection['selected_sessions']) != {f'D2-{number:02d}' for number in range(1, 5)}:
    raise SystemExit('D2-01..04 selection is incomplete')
attempts = []
for path in Path('data/raw').glob('*/session.json'):
    session = json.loads(path.read_text())
    if session.get('experiment_id') != 'mac-mac-iperf3-fixed-v2':
        continue
    if session.get('run_status') == 'running':
        raise SystemExit(f'Another formal v2 session is running: {path}')
    notes = session.get('environment_notes') or ''
    if 'slot_id=D2-05' in notes:
        attempts.append(session['session_id'])
    if any(f'slot_id=D2-{number:02d}' in notes for number in range(6, 9)):
        raise SystemExit(f'Unexpected D2-06..08 attempt: {path}; inspect before retrying')
if attempts != ['burst-20261025T065340Z-9683aa12']:
    raise SystemExit(f'Expected exactly the failed first D2-05 attempt, found: {attempts}')
load = json.loads(Path('data/load/burst-20261025T065340Z-b4a8d19a/run.json').read_text())
if load.get('status') != 'failed':
    raise SystemExit('First D2-05 burst load has not failed as expected')
PY

batch_dir=$(mktemp -d "data/load/fixed-formal-v2-d2-05-retry-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
exec > >(tee "$batch_dir/batch.log") 2>&1
printf 'Retry log: %s/batch.log\n' "$batch_dir"
printf 'Experiment: mac-mac-iperf3-fixed-v2; D2-05 burst 460 Mbps seed 104 only\n'
printf 'Excluded prior attempt: burst-20261025T065340Z-9683aa12\n'
printf 'Starting D2-05 burst retry at %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if ! bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh burst "$server_ip" "$wifi_iface" 104 2>&1 | tee "$batch_dir/D2-05.log"; then
  echo 'D2-05 retry load/collector failed; preserve and inspect all logs' >&2
  exit 1
fi
session_path=$(sed -n 's@^Session completed and saved to \(data/raw/[^ ]*\)$@\1@p' "$batch_dir/D2-05.log" | tail -1)
[[ -n $session_path ]] || { echo 'D2-05 retry has no completed session path' >&2; exit 1; }
python3 scripts/check_fixed_formal_v2_slot.py "$session_path" D2-05 burst
printf 'Finished and checked D2-05 retry: %s at %s\n' "$session_path" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

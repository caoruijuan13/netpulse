#!/usr/bin/env bash
# Run a preassigned slot with the frozen two-MacBook protocol.
set -euo pipefail

usage() {
  printf '%s\n' \
    'Usage:' \
    '  bash scripts/mac_mac_iperf3_formal.sh calibrate <SERVER_IP> <WIFI_IFACE>' \
    '  bash scripts/mac_mac_iperf3_formal.sh <SLOT_ID> idle <SERVER_IP> <WIFI_IFACE>' \
    '  bash scripts/mac_mac_iperf3_formal.sh <SLOT_ID> upload|download <SERVER_IP> <WIFI_IFACE> <CALIBRATION_SUMMARY_JSON>' \
    '  bash scripts/mac_mac_iperf3_formal.sh <SLOT_ID> burst <SERVER_IP> <WIFI_IFACE> <CALIBRATION_SUMMARY_JSON> <SEED>'
}

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
export NETPULSE_EXPERIMENT_CONFIG="$repo_dir/configs/mac-mac-iperf3-v1.toml"

if [[ ${1:-} == calibrate ]]; then
  [[ $# -eq 3 ]] || { usage >&2; exit 2; }
  exec bash scripts/mac_mac_iperf3_trial.sh "$@"
fi

[[ $# -ge 4 ]] || { usage >&2; exit 2; }
slot_id=$1
mode=$2
[[ $slot_id =~ ^D[1-4]-0[1-8]$ ]] || { echo 'SLOT_ID must be D1-01 through D4-08' >&2; exit 2; }
if [[ $mode == idle ]]; then
  [[ $# -eq 4 ]] || { usage >&2; exit 2; }
elif [[ $mode == upload || $mode == download ]]; then
  [[ $# -eq 5 ]] || { usage >&2; exit 2; }
elif [[ $mode == burst ]]; then
  [[ $# -eq 6 ]] || { usage >&2; exit 2; }
else
  usage >&2
  exit 2
fi
python3 scripts/check_formal_slot.py "$slot_id" "$mode" "${6:-}"
export NETPULSE_SLOT_ID=$slot_id

if [[ $mode == idle ]]; then
  wifi_ip=$(ipconfig getifaddr "$4") || { echo "No IPv4 address on $4" >&2; exit 1; }
  route_iface=$(route -n get "$3" | awk '/^[[:space:]]*interface:/ { print $2; exit }')
  if [[ $route_iface != "$4" ]]; then
    printf 'Route to %s uses %s, not %s. Fix the route before testing.\n' "$3" "$route_iface" "$4" >&2
    exit 1
  fi
  exec env PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
    --config "$NETPULSE_EXPERIMENT_CONFIG" \
    --target "$3" --scenario idle \
    --source-interface "$4" --source-link wifi --target-link ethernet \
    --environment-notes "Both MacBooks on power; VPN off; slot_id=$slot_id"
fi

shift
exec bash scripts/mac_mac_iperf3_trial.sh "$@"

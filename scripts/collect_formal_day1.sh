#!/usr/bin/env bash
# Run the eight preassigned D1 sessions in order, with manual server/log checks.
set -euo pipefail

usage() {
  printf '%s\n' \
    'Usage: bash scripts/collect_formal_day1.sh <SERVER_IP> <WIFI_IFACE> <CALIBRATION_SUMMARY_JSON> [--from D1-XX] [--dry-run]' \
    'Runs D1-01 through D1-08 sequentially. Start a fresh iperf3 server on the old Mac before each loaded slot.'
}

[[ $# -ge 3 ]] || { usage >&2; exit 2; }
server_ip=$1
wifi_iface=$2
calibration_summary=$3
shift 3
start_slot=D1-01
dry_run=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --from)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      start_slot=$2
      shift 2
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    *) usage >&2; exit 2 ;;
  esac
done

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
[[ -f $calibration_summary ]] || { printf 'Calibration summary not found: %s\n' "$calibration_summary" >&2; exit 1; }
python3 scripts/summarize_iperf3_calibration.py --capacity upload "$calibration_summary" >/dev/null
python3 scripts/summarize_iperf3_calibration.py --capacity download "$calibration_summary" >/dev/null

slots=(D1-01 D1-02 D1-03 D1-04 D1-05 D1-06 D1-07 D1-08)
modes=(idle upload download burst download burst idle upload)
seeds=('' '' '' 101 '' 102 '' '')
start_index=-1
for ((i=0; i<${#slots[@]}; i++)); do
  python3 scripts/check_formal_slot.py "${slots[$i]}" "${modes[$i]}" "${seeds[$i]}"
  if [[ ${slots[$i]} == "$start_slot" ]]; then
    start_index=$i
  fi
done
[[ $start_index -ge 0 ]] || { printf 'Unknown D1 slot: %s\n' "$start_slot" >&2; exit 2; }

if [[ $dry_run == false && ! -t 0 ]]; then
  echo 'Interactive terminal required for server changes and per-session review; use --dry-run to preview.' >&2
  exit 2
fi

printf 'D1: eight sequential 900-second sessions, beginning at %s. No scenarios run concurrently.\n' "$start_slot"
for ((i=start_index; i<${#slots[@]}; i++)); do
  slot=${slots[$i]}
  mode=${modes[$i]}
  seed=${seeds[$i]}
  printf '\n[%s] %s\n' "$slot" "$mode"
  if [[ $mode == idle ]]; then
    echo 'Old Mac: stop iperf3, then run caffeinate -i in its terminal to stay awake for ICMP (Ctrl-C after idle).'
    command=(bash scripts/mac_mac_iperf3_formal.sh "$slot" idle "$server_ip" "$wifi_iface")
  else
    printf 'Old Mac: stop the previous server, then start a fresh one with a unique %s server log:\n' "$slot"
    printf '  mkdir -p netpulse-server-logs\n'
    printf '  caffeinate -i iperf3 -s -i 1 --logfile "netpulse-server-logs/%s-$(date -u +%%Y%%m%%dT%%H%%M%%SZ)-server.log"\n' "$slot"
    if [[ $mode == burst ]]; then
      command=(bash scripts/mac_mac_iperf3_formal.sh "$slot" burst "$server_ip" "$wifi_iface" "$calibration_summary" "$seed")
    else
      command=(bash scripts/mac_mac_iperf3_formal.sh "$slot" "$mode" "$server_ip" "$wifi_iface" "$calibration_summary")
    fi
  fi
  printf 'New Mac: '
  printf '%q ' "${command[@]}"
  printf '\n'
  if [[ $dry_run == true ]]; then
    continue
  fi

  read -r -p 'After preparing the old Mac, press Enter to start this slot (q to stop): ' answer
  [[ $answer != q ]] || { echo "Stopped before $slot; resume later with --from $slot."; exit 0; }
  if ! "${command[@]}"; then
    printf 'Session command failed at %s. Keep its raw files; investigate before resuming with --from %s.\n' "$slot" "$slot" >&2
    exit 1
  fi
  read -r -p 'Review the RTT/load/server logs. Enter to continue, or q to stop: ' answer
  if [[ $answer == q ]]; then
    echo "Stopped after $slot; use --from for the next unfinished slot."
    exit 0
  fi
done
if [[ $dry_run == true ]]; then
  echo 'Dry run complete; no sessions were started.'
else
  echo 'D1 commands completed. Audit all eight sessions before treating D1 as accepted training data.'
fi

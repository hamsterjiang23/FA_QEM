#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: monitor_wsl_pid.sh PID OUTPUT_CSV INTERVAL_SECONDS [WATCH_DIRECTORY]" >&2
  exit 2
fi

pid="$1"
output="$2"
interval="$3"
watch_directory="${4:-}"

mkdir -p "$(dirname "$output")"
printf 'timestamp_utc,pid,elapsed_seconds,cpu_percent,rss_kib,vsz_kib,cpu_time,disk_bytes\n' >"$output"
while kill -0 "$pid" 2>/dev/null; do
  read -r elapsed cpu_percent rss_kib vsz_kib cpu_time < <(
    ps -p "$pid" -o etimes=,pcpu=,rss=,vsz=,time=
  )
  disk_bytes=0
  if [[ -n "$watch_directory" && -d "$watch_directory" ]]; then
    disk_bytes="$(du -sb "$watch_directory" | cut -f1)"
  fi
  printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pid" "$elapsed" "$cpu_percent" \
    "$rss_kib" "$vsz_kib" "$cpu_time" "$disk_bytes" >>"$output"
  sleep "$interval"
done

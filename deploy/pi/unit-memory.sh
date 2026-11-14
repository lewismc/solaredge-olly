#!/bin/bash
# Write cgroup memory for each SolarEdge unit to node_exporter's textfile collector.
# RSS overstates the risk for Alloy: most of it is file-backed pages of the binary,
# which the kernel reclaims at memory.max. anon is what an OOM kill is about.
set -euo pipefail

DIR="${UNIT_MEMORY_DIR:-/var/lib/node_exporter/textfile}"
OUT=$DIR/unit-memory.prom
UNITS="alloy solaredge-exporter solaredge-geolocate synthetic-monitoring-agent node-exporter sunspec-sim"

tmp=$(mktemp "$DIR/.unit-memory.XXXXXX")
trap 'rm -f "$tmp"' EXIT

{
  echo "# HELP solaredge_unit_memory_bytes cgroup memory of a systemd unit, by kind (current, anon, file, swap)."
  echo "# TYPE solaredge_unit_memory_bytes gauge"
  echo "# HELP solaredge_unit_memory_max_bytes memory.max of a systemd unit (MemoryMax=)."
  echo "# TYPE solaredge_unit_memory_max_bytes gauge"
  echo "# HELP solaredge_unit_memory_events_total memory.events counters of a systemd unit."
  echo "# TYPE solaredge_unit_memory_events_total counter"
  for u in $UNITS; do
    cg=/sys/fs/cgroup/system.slice/$u.service
    [ -r "$cg/memory.current" ] || continue
    unit="$u.service"
    echo "solaredge_unit_memory_bytes{unit=\"$unit\",kind=\"current\"} $(cat "$cg/memory.current")"
    echo "solaredge_unit_memory_bytes{unit=\"$unit\",kind=\"swap\"} $(cat "$cg/memory.swap.current" 2>/dev/null || echo 0)"
    awk -v u="$unit" '$1 == "anon" || $1 == "file" { printf "solaredge_unit_memory_bytes{unit=\"%s\",kind=\"%s\"} %s\n", u, $1, $2 }' "$cg/memory.stat"
    max=$(cat "$cg/memory.max")
    [ "$max" = "max" ] || echo "solaredge_unit_memory_max_bytes{unit=\"$unit\"} $max"
    awk -v u="$unit" '$1 == "max" || $1 == "oom_kill" { printf "solaredge_unit_memory_events_total{unit=\"%s\",event=\"%s\"} %s\n", u, $1, $2 }' "$cg/memory.events"
  done
} > "$tmp"

chmod 0644 "$tmp"
mv "$tmp" "$OUT"
trap - EXIT

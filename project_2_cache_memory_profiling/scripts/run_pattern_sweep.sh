#!/usr/bin/env bash
# Step 2: pattern (seq vs rand) x stride (64 / 256 / 1024 B) sweep.
# Working set 1 GiB (far beyond the 32 MiB L3) so every access is served by DRAM.
#   Latency:   pchase  (dependent loads, one at a time)
#   Bandwidth: bwbench (independent loads, many in flight), 1 thread
# Usage: scripts/run_pattern_sweep.sh [cpu] [reps]
set -euo pipefail
cd "$(dirname "$0")/.."
CPU="${1:-2}"; REPS="${2:-5}"; SIZE=1G
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p data/raw
scripts/env_capture.sh "data/raw/env_pattern_${TS}.txt"
LAT="data/raw/pattern_latency_${TS}.csv"
BW="data/raw/pattern_bandwidth_${TS}.csv"
./pchase -H > "$LAT"
./bwbench -H > "$BW"
for p in seq rand; do
  for s in 64 256 1024; do
    echo "pattern=$p stride=$s" >&2
    ./pchase  -s $SIZE -S $s -p $p -k 1 -c "$CPU" -r "$REPS" -n 20M >> "$LAT"
    ./bwbench -s $SIZE -S $s -p $p -m 100 -t 1 -c "$CPU" -r "$REPS" >> "$BW"
  done
done
echo "results: $LAT $BW"

#!/usr/bin/env bash
# Step 3: read/write mix sweep - 100% read, 70/30, 50/50, 100% write.
# Sequential, 64 B stride (every byte of every line used), 1 GiB (DRAM).
# Run with 1 thread and with all 16 physical cores, since one core alone
# usually cannot saturate DRAM.
# Usage: scripts/run_rw_sweep.sh [reps]
set -euo pipefail
cd "$(dirname "$0")/.."
REPS="${1:-5}"; SIZE=1G
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p data/raw
scripts/env_capture.sh "data/raw/env_rw_${TS}.txt"
OUT="data/raw/rw_mix_${TS}.csv"
./bwbench -H > "$OUT"
for t in 1 16; do
  for m in 100 70 50 0; do
    echo "threads=$t read_pct=$m" >&2
    ./bwbench -s $SIZE -S 64 -p seq -m $m -t $t -c 2-7,0,1,8-15 -r "$REPS" -b 8G >> "$OUT"
  done
done
echo "results: $OUT"

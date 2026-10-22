#!/usr/bin/env bash
# Working-set sweep + zero-queue baselines.
# Single chain (k=1), random order, 64 B stride, pinned to one core, huge pages
# (so TLB misses don't blur the cache staircase; TLB effects get their own test).
#
# Usage: scripts/run_ws_sweep.sh [cpu] [reps]
set -euo pipefail
cd "$(dirname "$0")/.."
CPU="${1:-2}"
REPS="${2:-5}"
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p data/raw
OUT="data/raw/ws_sweep_${TS}.csv"

scripts/env_capture.sh "data/raw/env_ws_sweep_${TS}.txt"

# ~1.5x steps from 4 KiB to 1 GiB, with extra points around each capacity edge
SIZES="4K 8K 16K 24K 32K 40K 48K 56K 64K 96K 128K 192K 256K 384K 512K 768K
       1M 1280K 1536K 2M 3M 4M 6M 8M 12M 16M 24M 28M 32M 40M 48M 64M 96M
       128M 256M 512M 1G"

./pchase -H > "$OUT"
for s in $SIZES; do
  echo "size $s" >&2
  ./pchase -s "$s" -k 1 -p rand -S 64 -P huge -c "$CPU" -r "$REPS" >> "$OUT"
done
echo "results: $OUT"

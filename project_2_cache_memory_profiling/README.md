# Project 2: Cache & Memory Performance Profiling

ECSE 4320/6320 Advanced Computer Systems — class-wide Project 2.

## Test machine

| Item | Value |
|---|---|
| CPU | AMD Ryzen 9 9950X (Zen 5), 16 cores / 32 threads, 1 socket, 1 NUMA node |
| L1d / L2 / L3 | 48 KiB per core (12-way) / 1 MiB per core (16-way) / 32 MiB per CCD (2 CCDs), 64 B lines |
| CCD layout | CCD 0 = CPUs 0–7 (+ SMT siblings 16–23), CCD 1 = CPUs 8–15 (+ 24–31) |
| Memory | 60 GiB |
| OS | CachyOS (Arch-based), THP = `always` |
| Frequency | `powersave` governor, boost on — not changeable (no root); see Limitations |

The exact state for every run is saved by `scripts/env_capture.sh` next to the raw data.

## Layout

```
src/pchase.c            pointer-chase latency / memory-level-parallelism benchmark
src/bwbench.c           bandwidth benchmark: stride, pattern, read/write mix, threads
src/chase_kernels.h     generated chase kernels (one per chain count)
scripts/gen_kernels.py  generates chase_kernels.h
scripts/env_capture.sh  records hardware, OS, governor, THP, tool versions
scripts/run_ws_sweep.sh working-set sweep + zero-queue baselines (Step 1)
scripts/run_pattern_sweep.sh  seq vs rand x 64/256/1024 B stride, latency + bandwidth (Step 2)
scripts/run_rw_sweep.sh read/write mix 100/70/50/0 % reads, 1 and 16 threads (Step 3)
data/raw/               raw CSV output + environment snapshots
```

## Build

```bash
make            # builds ./pchase (-O2) and ./bwbench (-O3), both -march=native
make check-asm  # shows the 1-chain inner loop: must be a single `mov (%rax),%rax`
```

## pchase

Builds a chain of pointers spread over a buffer and walks it. Every load depends
on the previous one, so time per load equals memory latency for that working set.
With `-k` chains walked in an interleaved way, up to `k` loads are in flight at once
(memory-level parallelism), which is used for the throughput–latency sweep.

| Flag | Meaning | Default |
|---|---|---|
| `-s SIZE` | Working-set size (`32K`, `1M`, `512M`, `1G`) | required |
| `-S BYTES` | Spacing between nodes; `4096` = one node per 4 KiB page | 64 |
| `-p rand\|seq` | Random (defeats prefetchers) or sequential visiting order | rand |
| `-k K` | Independent chains: 1, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32 | 1 |
| `-P thp\|4k\|huge` | Page policy: system default / `MADV_NOHUGEPAGE` / `MADV_HUGEPAGE` | huge |
| `-c CPU` | Pin to this CPU (`-1` = no pinning) | 2 |
| `-r REPS` | Timed repetitions (one CSV row each) | 5 |
| `-n N` | Loads per repetition | max(nodes, 10M) |
| `-w MS` | Busy-spin warm-up so the core ramps its clock | 200 |
| `-x SEED` | RNG seed (fixed by default for reproducibility) | fixed |
| `-H` | Print the CSV header | — |

### Output columns

| Column | Meaning |
|---|---|
| `ns_per_load` | Wall time / total loads. With `k = 1` this is the latency. |
| `cycles_per_load` | Core cycles / loads, from a user-space hardware counter (`perf_event_open`). Not affected by clock-speed changes. |
| `lat_ns_per_chain` | `ns_per_load × k`: the latency each individual load saw (y-axis of the intensity plot) |
| `eff_ghz` | Cycles / ns during the run: the clock the core actually ran at |
| `mb_per_s` | Bytes moved per second (64 B per load, or the stride if smaller) |
| `anon_huge_kb` | `AnonHugePages` for the process: proves whether huge pages were actually used |

### Correctness checks (built in)

- Before timing, every chain is walked once to confirm it is a single cycle that
  visits each node exactly once and returns to its start; the run aborts otherwise.
- The buffer's huge-page backing is read from `/proc/self/smaps_rollup` and recorded.
- `make check-asm` confirms the timed loop is only dependent loads.

### Design notes and pitfalls caught

- **Chain pointers must live in registers.** The first version stored the `k` chain
  pointers in a small array. Checking the disassembly showed GCC kept the array on
  the stack (and vectorized it), which adds store-to-load forwarding latency to every
  step and would inflate L1 latency. The kernels are now generated with one named
  variable per chain (`scripts/gen_kernels.py`). With 16 or more chains some
  pointers spill to the stack (x86-64 has ~14 free registers); the added few cycles
  are negligible against DRAM latency.
- **THP is `always` on this machine.** A "4 KiB page" test that doesn't set
  `MADV_NOHUGEPAGE` silently gets 2 MiB pages. `-P 4k` sets it explicitly and
  `anon_huge_kb` shows the result.
- **Frequency.** The governor can't be changed without root, so the benchmark
  warms up first and reports cycles alongside nanoseconds.

## bwbench

Streams through a buffer with independent accesses, so many cache misses are in
flight at once: the result is throughput (GB/s), not latency. The unit of work is
one 64 B cache line ("chunk"); reads sum its 8 words, writes store 8 words.

| Flag | Meaning | Default |
|---|---|---|
| `-s SIZE` | Total working set, split evenly across threads | required |
| `-S BYTES` | Distance between chunk starts: 64 = contiguous, 256 = 1 of every 4 lines | 64 |
| `-p seq\|rand` | Chunk visiting order | seq |
| `-m READPCT` | Percent of chunks that are reads: 100, 70, 50, 0 | 100 |
| `-t THREADS` | Thread count; each thread gets its own region | 1 |
| `-c CPUS` | CPUs to pin threads to, in order | `2-7,0,1,8-15` |
| `-P thp\|4k\|huge` | Page policy, as in pchase | huge |
| `-r REPS` | Timed repetitions | 5 |
| `-b BYTES` | Bytes touched per repetition (all threads) | 4G |
| `-H` | Print CSV header | — |

Notes:
- `gb_per_s` counts the 64 B chunks touched. For writes, real DRAM traffic is about
  2x: a normal store first reads the line in ("read for ownership"), then writes it back.
- The random pattern reads a 4 B index per chunk from a sequential index array;
  this adds about 6% extra traffic at stride 64.
- All threads start together at a barrier; time runs until the last one finishes.

## Running

```bash
make
scripts/run_ws_sweep.sh 2 5       # Step 1: CPU 2, 5 repetitions per size
scripts/run_pattern_sweep.sh 2 5  # Step 2
scripts/run_rw_sweep.sh 5         # Step 3
```

## Limitations

- No root access: governor (`powersave`) and boost could not be fixed, hardware
  prefetchers could not be disabled, and only user-space counters are available.
- Intel MLC was not used; on AMD it runs only partly and several modes need root.

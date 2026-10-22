# Project 2 – Cache & Memory Performance Profiling

This project was completed for ECSE 6320: Advanced Computer Systems. It characterizes the cache and
memory hierarchy of an AMD Ryzen 9 9950X (Zen 5) on CachyOS Linux, using two purpose-built C
benchmarks in place of Intel MLC: a pointer-chase latency benchmark and a streaming bandwidth benchmark.
Full environment: `env/` and the `env.txt` saved with every result session.

## Report

- Report.pdf, Report.tex, Report.md: *to be added in `report/`*

## AI use

- AI-use note: *to be added to the report*

## How to reproduce

On the Linux test machine, from this folder (Python 3 standard library only; plots need matplotlib):

```bash
make                                  # builds ./pchase (-O2) and ./bwbench (-O3), -march=native
make check-asm                        # 1-chain loop must be a bare `mov (%rax),%rax`
python3 scripts/membench.py --help    # commands; 'run --help' lists every knob
python3 scripts/membench.py list      # experiments and hypotheses
python3 scripts/membench.py env       # env/system_info_<time>.txt

python3 scripts/membench.py run sanity baseline
python3 scripts/membench.py run ws
python3 scripts/membench.py run pattern rw --shuffle
python3 scripts/membench.py run mlp loaded
python3 scripts/membench.py run tlb --shuffle

python3 scripts/membench.py parse     # -> results/processed/*.csv
python3 -m pip install --user matplotlib
cd analysis && python3 plot_ws.py && python3 plot_sweeps.py && python3 plot_intensity.py
```

Run long sessions inside `tmux`, with no other users on the machine (`who`, `uptime`).

## Headline results

*To be filled in after the runs.*

| Metric | Result | Setting |
|---|---|---|
| L1 load-to-use latency | 4.0 cycles (0.92 ns at 4.37 GHz) — preliminary | 32 KiB, random chase, CPU 2 |
| L2 / L3 / DRAM latency | | |
| Single-thread / all-core DRAM bandwidth | | |
| Knee (loads in flight) | | |
| TLB penalty, 4 KiB vs 2 MiB pages | | |

## Test system

| Item | Value |
|---|---|
| Machine | Lab workstation `TIESLabSamit`, accessed over SSH, standard user (no root) |
| CPU | AMD Ryzen 9 9950X (Zen 5, family 26), 16 cores / 32 threads, 1 socket, 1 NUMA node |
| Caches | L1d 48 KiB/core (12-way), L2 1 MiB/core (16-way), L3 32 MiB per CCD × 2 CCDs (16-way), 64 B lines |
| CCD layout | CCD 0 = CPUs 0–7 (SMT siblings 16–23), CCD 1 = CPUs 8–15 (SMT siblings 24–31) |
| Memory | 60 GiB DRAM |
| OS | CachyOS (Arch-based, rolling), transparent huge pages = `always` |
| Frequency | `powersave` governor, boost enabled (observed 0.62–5.76 GHz range); not changeable without root |
| Tools | gcc, perf 7.2 (user-space install), counters read in-process via `perf_event_open`, `perf_event_paranoid` = 2 |

## Repository layout

| Path | Contents |
|---|---|
| `src/pchase.c` | Pointer-chase benchmark: latency, memory-level parallelism (k chains), page-size control, in-process cycle / L1D / dTLB counters, chain self-validation |
| `src/bwbench.c` | Bandwidth benchmark: 64 B chunks, stride, seq/rand order, read/write mix, pinned threads |
| `src/chase_kernels.h` | Generated chase loops, one per chain count (`scripts/gen_kernels.py`) |
| `scripts/membench.py` | Runs every experiment (`list`, `run`, `env`, `parse`; see `--help`). Saves commands, output and manifests |
| `scripts/env_capture.sh` | Records CPU, caches, topology, governor, THP, SMT, load, tool versions |
| `results/raw/<experiment>/<session>/` | One CSV per point (`<point>.csv`), stderr log (`<point>.log`), background-load output for `loaded` (`<point>_load.csv`), `env.txt`, `manifest.json` (commands, knobs, hypothesis, versions, timestamps) |
| `results/processed/summary.csv` | One row per repetition |
| `results/processed/summary_agg.csv` | n, median, mean, std, min, max per point (median + min–max used for error bars) |
| `results/processed/baseline.md`, `sanity.md` | Baseline and pitfall-demo tables |
| `analysis/` | Parser and plotting scripts (below) |
| `figures/` | All plots |
| `env/` | System snapshots |
| `report/` | Final report |

## Experiments

Each point runs pinned to one core (default CPU 2) after a 200 ms warm-up and one untimed lap over the
working set; repetitions are in-process.

| Experiment | What it measures | Hypothesis | Outcome |
|---|---|---|---|
| `sanity` | Pitfalls: seq vs rand chase at 1 GiB; THP default vs forced 4 KiB pages, one access per page | Seq chase several × faster (prefetcher); THP default shows few dTLB misses | *pending* |
| `baseline` | Zero-queue latency at 32 KiB / 512 KiB / 16 MiB / 1 GiB (L1/L2/L3/DRAM), 10 reps | L1 ~4 cycles, L2 ~14, L3 ~50, DRAM ~80–100 ns | *pending* (L1 4.0 cycles in first test) |
| `ws` | Latency vs working set, 4 KiB–1 GiB, 37 sizes | Plateaus with steps past 48 KiB, 1 MiB, 32 MiB | *pending* |
| `pattern` | Seq vs rand × 64/256/1024 B stride at 1 GiB: latency + 1-thread bandwidth | Seq ≫ rand at 64 B; gap shrinks as stride grows | *pending* |
| `rw` | Bandwidth at 100/70/50/0 % reads, 1 and 16 threads | Bandwidth falls as write share rises | *pending* |
| `mlp` | 1 thread, 1–32 independent chains at 1 GiB: bandwidth vs per-load latency | Linear rise, then knee at the core's miss-handling limit | *pending* |
| `loaded` | One chain's latency while 0–14 other cores stream reads | Flat until near peak bandwidth, then sharp rise | *pending* |
| `tlb` | One access per 4 KiB page, 4 MiB–1 GiB, 4 KiB vs 2 MiB pages, dTLB misses | 4 KiB pages: misses and latency jump past TLB reach | *pending* |

## Benchmarks

### pchase (latency)

Every load's address comes from the previous load (`p = *p`), so loads cannot overlap and the time per
load is the latency. Nodes are linked in a shuffled order so the prefetcher cannot predict the next one.

| Flag | Meaning | Default |
|---|---|---|
| `-s SIZE` | Working-set size (`32K`, `1M`, `1G`) | required |
| `-S BYTES` | Node spacing; `4096` = one node per page | 64 |
| `-p rand\|seq` | Visiting order | rand |
| `-k K` | Independent chains (1, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32) | 1 |
| `-P thp\|4k\|huge` | System default / `MADV_NOHUGEPAGE` / `MADV_HUGEPAGE` | huge |
| `-c CPU`, `-r REPS`, `-n LOADS`, `-w MS`, `-x SEED`, `-H` | Pin CPU, repetitions, loads per rep, warm-up, seed, header | 2, 5, max(nodes, 10M), 200, fixed |

Output columns: `ns_per_load`, `cycles_per_load` (clock-independent), `lat_ns_per_chain` (= ns × k),
`eff_ghz` (actual clock), `mb_per_s`, `l1d_miss_per_load`, `dtlb_miss_per_load`, `anon_huge_kb`
(proves whether huge pages were used). Counters cover only the timed loop.

### bwbench (bandwidth)

Accesses are independent, so many misses are in flight; the result is throughput. The unit is one 64 B
line: reads sum its 8 words, writes store 8 words.

| Flag | Meaning | Default |
|---|---|---|
| `-s SIZE` | Total working set, split across threads | required |
| `-S BYTES` | Distance between chunks (64 = contiguous) | 64 |
| `-p seq\|rand`, `-m READPCT` | Order; percent of chunks that are reads | seq, 100 |
| `-t N`, `-c CPUS` | Threads; CPU list they are pinned to in order | 1, `2-7,0,1,8-15` |
| `-P`, `-r`, `-b BYTES`, `-H` | Pages, repetitions, bytes per rep, header | huge, 5, 4G |

`gb_per_s` counts chunks touched; for writes real DRAM traffic is ~2× (read-for-ownership + write-back).
The random pattern also reads a 4 B index per chunk (~6 % extra at 64 B stride).

## Analysis scripts and figures

| Script | Figures / tables | Shows |
|---|---|---|
| `parse_results.py` | — | All raw CSVs → `summary.csv`, `summary_agg.csv` |
| `plot_ws.py` | `ws_latency.png`, `ws_cycles.png` | Latency staircase in ns and cycles, cache capacities marked |
| | `results/processed/baseline.md` | Zero-queue baseline table |
| `plot_sweeps.py` | `pattern_latency.png`, `pattern_bw.png` | Seq vs rand across strides |
| | `rw_bw.png` | Bandwidth vs read/write mix |
| | `tlb_latency.png`, `tlb_misses.png` | 4 KiB vs 2 MiB pages |
| | `results/processed/sanity.md` | Pitfall demos |
| `plot_intensity.py` | `mlp_tradeoff.png` | Throughput vs latency as loads in flight grow (knee) |
| | `mlp_littles.png` | Little's Law: measured outstanding misses vs k |
| | `loaded_latency.png` | Latency vs background bandwidth |

## Design notes and pitfalls caught

- **Chain pointers must live in registers.** A first version kept the k chain pointers in an array;
  `objdump` showed GCC kept it on the stack (and vectorized it), adding store-forwarding latency to every
  step. Kernels are now generated with one variable per chain; `make check-asm` verifies the loop.
- **THP is `always`.** A "4 KiB page" test without `MADV_NOHUGEPAGE` silently gets 2 MiB pages;
  `pchase -P 4k` forces 4 KiB pages and `anon_huge_kb` records what was used.
- **Clock warm-up.** The first `bwbench` repetition ran at 70 GB/s vs 88 GB/s for later ones while the
  core ramped up; results use medians, and every point warms up first.
- **`bwbench` in L1/L2 is instruction-bound**, not cache-bound (~20 B/cycle); it is used for DRAM-sized
  working sets, where memory is the bottleneck.

## Limitations

- **No root access:** governor (`powersave`) and boost could not be fixed; latencies are also reported
  in cycles, and the actual clock is recorded per repetition (`eff_ghz`).
- **Hardware prefetchers could not be disabled** (needs MSR access); randomized order defeats them for
  latency measurements.
- **Only user-space counters** (`perf_event_paranoid` = 2); AMD L3 (uncore) counters were unavailable.
- **Intel MLC not used:** on AMD it runs only partly and several modes need root.
- **Shared lab machine:** runs were done with no other users logged in; load average is recorded per session.

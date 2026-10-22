# ECSE 6320 – Class-wide Projects

Rashid Shabab · ECSE 4320/6320 Advanced Computer Systems, Fall 2026

This repository holds my three class-wide projects. Each folder is self-contained, with
its own source code, run scripts, raw and processed data, plotting scripts, figures,
report (PDF, LaTeX and Markdown) and README with reproduction steps.

| Project | Topic | Platform | Report |
|---|---|---|---|
| [Project 1](project_1_simd_adv_profiling/) | SIMD advantage profiling | Intel Core Ultra 7 265H, WSL2, GCC 15.2 | [PDF](project_1_simd_adv_profiling/report/Report.pdf) |
| [Project 2](project_2_cache_memory_profiling/) | Cache & memory performance profiling | AMD Ryzen 9 9950X (Zen 5), CachyOS Linux, GCC 16.2 | [PDF](project_2_cache_memory_profiling/report/Report.pdf) |
| [Project 3](project_3_ssd_profiling/) | SSD performance profiling | Samsung PM9E1 2 TB NVMe, Windows 11, FIO 3.43 | [PDF](project_3_ssd_profiling/report/Report.pdf) |

## Project 1 – SIMD Advantage Profiling

Scalar vs auto-vectorized vs native builds of SAXPY, a strict dot product and a
three-point stencil, across float32/float64, working-set size, alignment, tail
handling and stride, with compiler reports and disassembly as vectorization evidence.
Float32 native SAXPY ran 5.8× faster than scalar in L1, but only 1.6× in DRAM, where
memory bandwidth limits both builds.

## Project 2 – Cache & Memory Performance Profiling

Three custom C benchmarks (pointer-chase latency, streaming bandwidth, SAXPY), used in
place of Intel MLC, measure zero-queue latency (L1 4.0, L2 14.0, L3 47.3 cycles; DRAM
97.9 ns), the working-set staircase, pattern/stride and read/write sweeps, the
single-core throughput–latency knee (~48 misses in flight), loaded latency, and the
impact of cache and TLB misses, with hardware counters read around the timed loop.

## Project 3 – SSD Performance Profiling

FIO characterization of an NVMe SSD with direct I/O on a 64 GiB test file: QD=1
baselines, block-size and read/write sweeps, the queue-depth knee with Little's Law,
peak throughput (553k IOPS random read, 6.9 GB/s sequential), tail latency, and burst
vs steady-state writes.

## Common requirements

Every project includes the items required for all class-wide projects:

| Requirement | Where to find it |
|---|---|
| AI-use note | The *AI-use note* section of each report |
| Reproducible repository | `src/`, `scripts/`, `analysis/`, `results/raw/`, `results/processed/` and the README in each project |
| Pre-experiment hypotheses | A hypothesis/outcome table in each report (Project 1 also has `report/HYPOTHESES.md`) |
| Correctness validation | The *Methodology* section of each report |
| Measurement discipline | `env/` and the per-run environment records in each project |
| Negative / failure case | The *Misleading setups* or *Benchmark pitfalls* section of each report |
| Honest anomalies | The *Anomalies* section of each report |

## AI use

These projects were completed with the help of Claude (Anthropic), which wrote most of
the code and helped draft the reports and READMEs. I also used an OpenAI assistant to
revise wording, formatting and section numbering in the reports. I ran all experiments
on my own hardware, and every reported number comes from the raw data in this
repository. Each report's AI-use note itemizes what the AI tools did, the errors they
made and how those errors were caught.

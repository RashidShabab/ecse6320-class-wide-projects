# ECSE 6320 – Class-wide Projects

Rashid Shabab · ECSE 6320 Advanced Computer Systems, Fall 2026

This repository holds my three class-wide projects. Each folder is self-contained, with
its own source code, run scripts, raw and processed data, plotting scripts, figures,
report (PDF, LaTeX and Markdown) and README with reproduction steps.

| Project | Topic | Platform | Report |
|---|---|---|---|
| [Project 1](project_1_simd_adv_profiling/) | SIMD advantage profiling | Intel Core Ultra 7 265H, WSL2, GCC 15.2 | [PDF](project_1_simd_adv_profiling/report/Report.pdf) |
| [Project 2](project_2_cache_memory_profiling/) | Cache & memory performance profiling | AMD Ryzen 9 9950X (Zen 5), CachyOS Linux, GCC 16.2 | [PDF](project_2_cache_memory_profiling/report/Report.pdf) |
| [Project 3](project_3_ssd_profiling/) | SSD performance profiling | Samsung PM9E1 2 TB NVMe, Windows 11, FIO 3.43 | [PDF](project_3_ssd_profiling/report/Report.pdf) |

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

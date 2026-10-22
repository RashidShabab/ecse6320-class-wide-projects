# Project 1 - SIMD Advantage Profiling

ECSE 6320: Advanced Computer Systems. Profiles SAXPY, strict dot product and a three-point stencil across scalar, default and native compiler builds, float32/float64, locality, alignment, tails and strides.

## Report

- [PDF report](report/Report.pdf)
- [LaTeX source](report/Report.tex)
- [Markdown report](report/Report.md)
- [SIMD compiler evidence](report/VECTORIZATION.md)
- [Pre-experiment hypotheses](report/HYPOTHESES.md)

Existing measurements contain 528 benchmark processes and 10,560 timed intervals, with no recorded correctness failures. Actual hardware core-cycle measurements remain unavailable on the original WSL host; TSC ticks are labeled separately. See the report for variability and limitations.

## How to reproduce

Use Linux/WSL on an x86-64 CPU supporting AVX2, FMA and RDTSCP, with GCC, binutils and Python 3. Run from this project directory. Select an available logical CPU if CPU 0 is unavailable.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/run.py build
python scripts/verify.py
python scripts/run.py tail --trials 3 --cpu 0
python scripts/run.py stride --trials 3 --cpu 0
python scripts/run.py locality --trials 3 --cpu 0
python scripts/run.py alignment --trials 3 --cpu 0
python scripts/run.py bandwidth --trials 3 --cpu 0
python analysis/analyze.py
python scripts/export_report.py --engine tectonic
```

Report export requires Tectonic or another LaTeX engine (`--engine pdflatex` also works). The exporter generates `report/Report.tex` from Markdown and compiles `report/Report.pdf`; the PDF and TeX use the seven existing figures. `report/Report.md` is written by hand; after regenerating the analysis, compare its numbers with `results/processed/generated_tables.md`, then run the exporter again.

Run benchmarks sequentially. Each sweep appends a timestamped result directory. Analysis selects the latest completed summary per study and overwrites processed tables, figures and the generated report. Error bars show between-process min/max, not confidence intervals.

## Headline results

Saved float32 native SAXPY locality results, medians of process medians:

| Region | GFLOP/s | Speedup versus scalar |
|---|---|---|
| L1 | 32.1 | 5.80x |
| L2 | 12.4 | 2.85x |
| L3 | 4.46 | 1.91x |
| DRAM | 3.15 | 1.62x |

These are historical measurements, not a fresh benchmark of the current environment.

## Repository layout

| Path | Contents |
|---|---|
| `src/` | C kernels, benchmark harnesses and reference validation |
| `scripts/run.py` | Six compiler builds, experiment sweeps and environment capture |
| `scripts/verify.py` | Optimized-reference and ASan/UBSan validation |
| `analysis/analyze.py` | Processed tables, seven figures and `results/processed/generated_tables.md` (never overwrites `Report.md`) |
| `results/raw/<timestamp>_<study>/` | Original plans, hypotheses, environment, raw JSONL and per-process summaries |
| `results/processed/` | Locality, alignment, tail and final summary CSVs |
| `figures/` | Seven final figures |
| `env/evidence/` | Compiler commands, vectorization reports, disassembly and recorded validation |
| `env/` | Compiler and validation evidence |
| `report/` | Main report, hypotheses and SIMD evidence |

Per-run `environment.json` files stay with their raw data to preserve provenance.

## Experiments and figures

| Study | Question | Figure |
|---|---|---|
| Locality | How does SIMD speedup change across intended cache/DRAM regimes? | `locality_speedup.png`, `locality_gflops.png` |
| Datatype | How do byte-matched float32 and float64 compare? | `datatype.png` |
| Alignment | What is the effect of a +4-byte shift? | `alignment.png` |
| Tail | What happens for every remainder modulo eight? | `tail.png` |
| Stride | When does the runtime stride prevent packed SIMD? | `stride.png` |
| Bandwidth | Is the observed speed consistent with an algorithmic roofline? | `roofline.png` |

## Environment and provenance

The saved experiments used an Intel Core Ultra 7 265H, WSL2 Linux 6.6.87.2 and GCC 15.2.0, pinned to logical CPU 0. Guest-visible cache sizes and host scheduling limitations are documented in the report. Dependency versions are in `requirements.txt`.

The four C files keep their `_v3` names to match the recorded compiler evidence and source hashes.

## AI use and limitations

See the AI-use note in the report. Review the methodology and findings before submission. Actual core-cycle data still needs a PMU-enabled host or instructor acceptance of the documented limitation. Reorganization does not resolve that requirement. Nothing has been pushed to GitHub.

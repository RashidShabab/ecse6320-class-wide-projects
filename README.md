# Project 3 – SSD Performance Profiling

This project was completed for ECSE 6320: Advanced Computer Systems. It characterizes a Samsung
PM9E1 2 TB NVMe SSD with FIO 3.43 on native Windows 11, using direct I/O against a disposable 64 GiB test file.
Full environment: [`env/system_info.txt`](env/system_info.txt).

## Report

- [Report.pdf](report/Report.pdf)
- [Report.tex](report/Report.tex) (LaTeX source)
- [Report.md](report/Report.md) (Markdown)

## AI use

- [AI-use note](report/Report.md#16-ai-use-note)

## How to reproduce

Windows PowerShell, from the repository root (`python` = Windows Python 3.12; WSL `python3` also works,
since it calls the Windows `fio.exe`):

```powershell
mkdir C:\fiotest -Force
python scripts\ssdbench.py --help               # commands; 'run --help' lists every knob
python scripts\ssdbench.py list                 # experiments, hypotheses, time estimates

python scripts\ssdbench.py run prep             # fill the 64 GiB test file (run twice)
python scripts\ssdbench.py run sanity qd1
python scripts\ssdbench.py run sanity --sanity-size 256M --ramp 30 --tag warmcache
python scripts\ssdbench.py run qd
python scripts\ssdbench.py run peak --shuffle
python scripts\ssdbench.py run bs mix range --shuffle
python scripts\ssdbench.py run tail --qd 4,16,64 --shuffle
python scripts\ssdbench.py run range --qd 1 --shuffle --tag qd1
python scripts\ssdbench.py run mix --qd 16 --numjobs 4 --shuffle --tag nj4
python scripts\ssdbench.py run steady --runtime 240 --yes    # writes ~600 GB

python scripts\ssdbench.py parse                # -> results/processed/*.csv
python -m pip install matplotlib
python analysis\plot_qd.py; python analysis\plot_peak.py; python analysis\plot_sweeps.py; python analysis\plot_steady.py
```

CPU clock logging (second window, during long runs; stop with Ctrl+C):

```powershell
typeperf "\Processor Information(_Total)\% Processor Performance" "\Processor Information(_Total)\% Processor Utility" -si 5 -o results\raw\<name>_cpu_log.csv
```

SMART data (temperature, data written, thermal-throttle counters) was read with CrystalDiskInfo
before and after each batch; screenshots are in `env/`.

## Headline results

| Metric | Result | Setting |
|---|---|---|
| QD=1 4 KiB random read | 67.8 µs mean, 165 µs p99 | 1 job |
| QD=1 4 KiB random write | 48.7 µs mean, 98 µs p99 | 1 job |
| Single-thread knee | QD 16, ~117k IOPS, 111 µs mean | 4 KiB random read, 1 job |
| Peak 4 KiB random read | 553k IOPS (best run 601k) | QD 32 × 8 jobs |
| Peak 128 KiB sequential read | 6,919 MB/s (88% of PCIe Gen4 x4 7,877 MB/s) | QD 8 × 4 jobs |
| Sustained write | ~27 GB burst at 6,760 MB/s, then ~1,800 MB/s | 128 KiB, QD 32, 240 s |

Main findings: the single-thread knee is set by the host CPU, not the SSD (Little's Law L ≈ ½ of
requested QD past the knee; IOPS scales with threads; IOPS vs CPU clock r = 0.75). Small blocks are
operation-bound, large blocks bandwidth-bound (switch between 32 and 64 KiB). Mixed read/write beats
the pure-workload average for throughput but raises read p99 ~70%. Burst write capacity depends on
the drive's recent write history.

## Test system

| Item | Value |
|---|---|
| Machine | Lenovo 21TES07S00 laptop, on AC power, High performance power plan |
| CPU | Intel Core Ultra 7 265H, 16 cores, no SMT, 2.2 GHz base (clock observed 3.3–5.25 GHz) |
| RAM | 64 GB LPDDR5X @ 7467 MT/s |
| OS | Windows 11 Education 10.0.26200, standard user (no admin rights) |
| SSD | SAMSUNG MZVLC2T0HBLD-00BLL (PM9E1), 2 TB, firmware 5L2QNXH7, NVMe 2.0 |
| Link | PCIe Gen4 x4 (drive supports Gen5 x4), verified idle and under load |
| Target | `C:\fiotest\testfile`, 64 GiB, NTFS (outside the repo) |
| FIO | 3.43, `ioengine=windowsaio`, `direct=1`, incompressible data, `randrepeat=0` |

## Repository layout

| Path | Contents |
|---|---|
| `scripts/ssdbench.py` | Runs every experiment (`list`, `run`, `parse`; see `--help`). Generates job files, refuses raw devices, saves manifests |
| `scripts/run_job.ps1`, `jobs/*.fio` | Earlier PowerShell runner and static job files (used for the first prep pass) |
| `results/raw/<experiment>/<session>/` | Generated `.fio`, one JSON per run (`*_r<N>.json`), `manifest.json` (all knobs, FIO version, timestamps) |
| `results/raw/*_cpu_log.csv` | CPU clock logged every 5 s with `typeperf` during `peak` and the later sweeps |
| `results/raw/00_prep_*.json`, `run_log.csv` | First prep pass via `run_job.ps1` |
| `results/processed/summary.csv` | One row per run, job and direction |
| `results/processed/summary_agg.csv` | Mean ± std across repetitions (used for error bars) |
| `analysis/` | Parser and plotting scripts (below) |
| `figures/` | All plots (below) |
| `env/` | System info and CrystalDiskInfo SMART screenshots |
| `report/` | Final report: `Report.pdf`, LaTeX source `Report.tex`, `Report.md`, and the figures it uses in `ssd_report_figures/` |

## Experiments

All points ran 3 times (30 s + 5 s warm-up, 10 s cool-down) unless noted. Later experiments used
`--shuffle` to randomize point order within each repetition.

| Experiment | What it measures | Results (under `results/raw/`) | Hypothesis | Outcome |
|---|---|---|---|---|
| `prep` | Fill test file, 1 MiB seq write, QD 16 (2 passes) | `00_prep_*.json` (pass 1), `prep/20261020_200758` (pass 2) | Several GB/s burst | Pass 1 2.8 GB/s with effective QD 8.8 (NTFS file extension); pass 2 5.2 GB/s, QD 15.7 |
| `sanity` | 4 KiB random read QD 1, direct vs buffered, 1 GiB region | `sanity/20261020_200812` | Buffered 10–100× faster | Partly: 3.5× (cache only partly warm) |
| `sanity --tag warmcache` | Same, 256 MiB region, 30 s warm-up | `sanity/20261020_202734_warmcache` | Fully cached reads much faster | 6.4× faster mean, 5× at p95 |
| `qd1` | QD 1: 4 KiB rand read/write, 128 KiB seq read/write | `qd1/20261020_200812` | Read 50–100 µs; writes faster | Supported: read 68 µs, write 49 µs |
| `qd` | QD 1–256, 4 KiB random read, 1 job | `qd/20261020_203435` | Linear rise, then knee | Knee at QD 16; Little's L ≈ ½ QD past it (host-bound) |
| `peak` | QD × numjobs grid, 4 KiB rand + 128 KiB seq read | `peak/20261020_221415` | One thread can't saturate | Supported: 553k IOPS at 8 jobs; seq 6.9 GB/s at link limit |
| `bs` | 4–256 KiB, random + sequential read, QD 32 | `bs/20261020_230654` | MB/s rises to link ceiling | Supported: op-bound ≤32 KiB, bandwidth-bound ≥64 KiB |
| `mix` | 100/70/50/0 % read, 4 KiB random, QD 32, 1 job | `mix/20261020_230654` | Mixes underperform average | Not testable: masked by single-thread limit |
| `mix --tag nj4` | Same, QD 16 × 4 jobs | `mix/20261021_002847_nj4` | Mixes underperform average | Refuted for IOPS (+7–15%); supported for read p99 (+~70%) |
| `range` | 1–64 GiB LBA range, 4 KiB random read, QD 32 | `range/20261020_230654` | Small ranges faster | No trend (CPU noise) |
| `range --tag qd1` | Same at QD 1 | `range/20261021_001938_qd1` | Small ranges faster | Not supported: flat 71–75 µs |
| `tail` | p50–p99.9 at QD 4, 16, 64; 120 s runs | `tail/20261020_235259` | Tails grow faster than p50 near knee | Supported: p99.9 +70% vs p50 +28% (QD 4→16) |
| `steady` | 128 KiB seq write, QD 32, 240 s, 1 s logs, 1 run | `steady/20261021_004515` | Drop when SLC cache fills | Supported: drop after ~27 GB, 6.76 → 1.8 GB/s; recovery bursts |

## Analysis scripts and figures

| Script | Figures | Shows |
|---|---|---|
| `parse_fio.py` | — | All JSON → `summary.csv`, `summary_agg.csv` (incl. Little's Law L = IOPS × mean latency) |
| `plot_qd.py` | `qd_tradeoff.png` | Throughput vs latency across QD (knee) |
| | `qd_littles.png` | Measured vs requested outstanding I/O |
| `plot_peak.py` | `peak_iops.png` | 4 KiB random IOPS vs numjobs |
| | `peak_seq.png` | 128 KiB sequential MB/s vs numjobs, PCIe ceiling |
| | `peak_cpu.png` | Per-run IOPS vs CPU clock (needs `peak_cpu_log.csv`) |
| `plot_sweeps.py` | `bs_bw.png`, `bs_iops.png`, `bs_lat.png` | Block-size sweep: MB/s, IOPS, latency |
| | `mix_iops.png`, `mix_iops_nj4.png` | Read/write mix, 1 job and 4 jobs |
| | `range_lat.png`, `range_lat_qd1.png` | LBA range at QD 32 and QD 1 |
| | `tail.png` | Latency percentiles at QD 4, 16, 64 |
| `plot_steady.py` | `steady.png` | Sustained write bandwidth and latency per second |

## Environment records (`env/`)

| File | When |
|---|---|
| `system_info.txt` | 2026-10-20 11:17, before testing |
| `crystaldiskinfo_20261020_2203.png` | Before `peak` |
| `crystaldiskinfo_20261020_2257_after_peak.png` | After `peak` |
| `crystaldiskinfo_20261021_0014_after_sweeps.png` | After `bs`, `mix`, `range`, `tail` |
| `crystaldiskinfo_20261021_0038_after_reruns.png` | After `range --tag qd1`, `mix --tag nj4` |
| `crystaldiskinfo_20261021_0049_after_steady.png` | After `steady` (summary totals not yet refreshed) |

Thermal-throttle counters stayed at 0 throughout. The project wrote ~1 TB and read ~11 TB in total.

## Limitations

- **CPU frequency not controllable** (no admin): clock varied 3.3–5.25 GHz; small-block IOPS correlates
  with it (r = 0.75), adding 10–30% run-to-run variation. Mitigated by logging, shuffling and mean ± std.
- **OS on the tested drive**: background Windows I/O adds noise, mainly to p99/p99.9.
- **NTFS file, not raw device**: small filesystem overhead; writes that extend a file are partly serialized
  (seen in prep pass 1). All measurements used the pre-written file.
- **Working set limited to 64 GiB** (~3% of the drive); mapping-cache effects beyond that are untested.
- **Single `steady` run**; burst size depends on recent write history, so no error bar.
- **Gen4 link on a Gen5 drive**: sequential results reflect the platform, not the drive's rated speed.
- **Hybrid CPU**: FIO threads may land on efficiency cores, possibly limiting multi-thread scaling.
- **No admin rights**: Defender real-time scanning stayed on; power states not controlled.

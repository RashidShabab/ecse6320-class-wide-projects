# Project 3 – SSD Performance Profiling

ECSE 4320/6320. Characterizes a Samsung PM9E1 2 TB NVMe SSD with FIO on native Windows 11.
Full environment: [`env/system_info.txt`](env/system_info.txt).

## Layout

| Folder | Contents |
|---|---|
| `env/` | System info, CrystalDiskInfo screenshots |
| `jobs/` | FIO job files, one per experiment, numbered in run order |
| `scripts/` | `ssdbench.py` – runs/parses all experiments; `run_job.ps1` – runs a static job file N times |
| `results/raw/` | FIO JSON output (never edited by hand) and `run_log.csv` |
| `results/processed/` | `summary.csv` (per run) and `summary_agg.csv` (mean ± std across reps) |
| `analysis/` | `parse_fio.py` and plotting scripts |
| `figures/` | Generated plots |
| `report/` | Report draft and AI-use note |

The 64 GiB test file lives at `C:\fiotest\testfile`, outside the repo.

## How to reproduce

### Recommended: `scripts/ssdbench.py`

One script runs every experiment, saves the generated FIO job file, JSON result and a
manifest (all knobs, fio version, timestamps) to `results/raw/<experiment>/<session>/`,
and parses everything into CSVs. Run from WSL (it calls the Windows `fio.exe`, so the
I/O itself is native Windows) or from Windows Python.

```bash
python3 scripts/ssdbench.py --help          # all commands
python3 scripts/ssdbench.py run --help      # all knobs
python3 scripts/ssdbench.py list            # experiments, hypotheses, time estimates
python3 scripts/ssdbench.py run prep        # fill the test file once
python3 scripts/ssdbench.py run all         # every experiment except prep and steady
python3 scripts/ssdbench.py parse           # -> results/processed/summary.csv, summary_agg.csv
```

### Alternative: PowerShell runner for the static job files

Windows PowerShell, from the repo root:

```powershell
mkdir C:\fiotest -Force
powershell -ExecutionPolicy Bypass -File scripts\run_job.ps1 -Job jobs\00_prep.fio -Reps 1
powershell -ExecutionPolicy Bypass -File scripts\run_job.ps1 -Job jobs\01_sanity_direct_vs_buffered.fio -Reps 3
powershell -ExecutionPolicy Bypass -File scripts\run_job.ps1 -Job jobs\02_qd1_baselines.fio -Reps 3
```

Then in WSL: `python3 analysis/parse_fio.py`

## Experiments and hypotheses

| # | Job file | Hypothesis |
|---|---|---|
| 00 | `00_prep.fio` | Fill only. Burst sequential write should be several GB/s (64 GiB fits in the SLC cache). |
| 01 | `01_sanity_direct_vs_buffered.fio` | Buffered reads over a 1 GiB region are served from RAM and show latency 10–100× lower than direct I/O. |
| 02 | `02_qd1_baselines.fio` | 4 KiB random read QD=1 ≈ 50–100 µs (flash read time + controller + OS stack). 4 KiB writes appear faster than reads because they are acknowledged from the controller's buffer. 128 KiB sequential reads are well below the ~7 GB/s PCIe Gen4 x4 ceiling at QD=1. |

## Known limitations

- No administrator rights: Defender real-time scanning stays on; SMART/temperature only via CrystalDiskInfo.
- OS runs on the same SSD: background I/O possible; mitigated by repeated runs.
- NTFS file, not raw device: small filesystem overhead; working set limited to 64 GiB.
- PCIe link reported as Gen4 x4 at idle on a Gen5-capable drive.

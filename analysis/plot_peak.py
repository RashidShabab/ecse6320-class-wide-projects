"""Peak-performance figures for the 'peak' experiment.

  figures/peak_iops.png  : 4 KiB random-read IOPS vs numjobs (QD 32 and 128)
  figures/peak_seq.png   : 128 KiB sequential-read MB/s vs numjobs, with the PCIe Gen4 x4 ceiling
  figures/peak_cpu.png   : per-run IOPS (relative to that setting's mean) vs CPU clock during the run
                           (needs a typeperf log, default results/raw/peak_cpu_log.csv)

Usage: python analysis/plot_peak.py [--session S] [--cpu-log PATH]
"""
import argparse
import csv
import datetime as dt
import json
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "results" / "processed"
RAW = ROOT / "results" / "raw"
FIG = ROOT / "figures"
INK, MUTED, GRID = "#1f2328", "#59636e", "#d8dee4"
C1, C2 = "#2a78d6", "#eb6834"
PCIE_GEN4_X4_MBPS = 16e9 * 4 * 128 / 130 / 8 / 1e6   # 7877 MB/s theoretical


def style(ax, title, subtitle):
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED)
    ax.set_title(title, color=INK, loc="left", fontsize=12, pad=18)
    ax.text(0, 1.01, subtitle, transform=ax.transAxes, fontsize=8, color=MUTED, va="bottom")


def series(ax, rows, key, scale, color, label):
    rows = sorted(rows, key=lambda r: int(r["numjobs"]))
    x = [int(r["numjobs"]) for r in rows]
    y = [float(r[f"{key}_mean"]) / scale for r in rows]
    e = [float(r[f"{key}_std"]) / scale for r in rows]
    ax.errorbar(x, y, yerr=e, color=color, linewidth=2, marker="o", markersize=6, capsize=3, label=label)
    ax.annotate(label, (x[-1], y[-1]), textcoords="offset points", xytext=(8, 0), va="center",
                fontsize=9, color=INK)
    return x


def cpu_log(path):
    out = []
    with path.open() as f:
        for line in list(csv.reader(f))[1:]:
            try:
                out.append((dt.datetime.strptime(line[0], "%m/%d/%Y %H:%M:%S.%f"), float(line[1])))
            except (ValueError, IndexError):
                pass
    return out


def pearson(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5
    return num / den if den else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", help="peak session folder (default: latest)")
    ap.add_argument("--cpu-log", default=str(RAW / "peak_cpu_log.csv"), help="typeperf CSV")
    a = ap.parse_args()
    FIG.mkdir(exist_ok=True)

    agg = [r for r in csv.DictReader((PROC / "summary_agg.csv").open())
           if r["experiment"] == "peak" and r["dir"] == "read"]
    session = a.session or max(r["session"] for r in agg)
    agg = [r for r in agg if r["session"] == session]
    n = agg[0]["n"]

    # 1. 4K random IOPS vs numjobs
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    style(ax, "4 KiB random read: IOPS scales with submitting threads",
          f"direct I/O, 64 GiB range, mean ± std of {n} reps")
    for qd, c in (("32", C1), ("128", C2)):
        x = series(ax, [r for r in agg if r["rw"] == "randread" and r["iodepth"] == qd],
                   "iops", 1e3, c, f"QD {qd} per job")
    ax.set_xscale("log", base=2)
    ax.set_xticks(x, [str(v) for v in x])
    ax.set_xlim(right=x[-1] * 1.9)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("numjobs (parallel FIO threads)", color=INK)
    ax.set_ylabel("Throughput (kIOPS)", color=INK)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "peak_iops.png")

    # 2. 128K sequential MB/s vs numjobs
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    style(ax, "128 KiB sequential read approaches the PCIe Gen4 x4 ceiling",
          f"direct I/O, 64 GiB range, mean ± std of {n} reps")
    for qd, c in (("8", C1), ("32", C2)):
        x = series(ax, [r for r in agg if r["rw"] == "read" and r["iodepth"] == qd],
                   "bw_MBps", 1, c, f"QD {qd} per job")
    ax.axhline(PCIE_GEN4_X4_MBPS, color=MUTED, linestyle="--", linewidth=1.5)
    ax.text(x[0], PCIE_GEN4_X4_MBPS + 80, f"PCIe Gen4 x4 theoretical ≈ {PCIE_GEN4_X4_MBPS:,.0f} MB/s",
            fontsize=8, color=MUTED)
    ax.set_xscale("log", base=2)
    ax.set_xticks(x, [str(v) for v in x])
    ax.set_xlim(right=x[-1] * 1.9)
    ax.set_ylim(0, PCIE_GEN4_X4_MBPS * 1.12)
    ax.set_xlabel("numjobs (parallel FIO threads)", color=INK)
    ax.set_ylabel("Throughput (MB/s)", color=INK)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "peak_seq.png")

    # 3. IOPS vs CPU clock
    log_path = Path(a.cpu_log)
    if not log_path.exists():
        print("no CPU log; skipped peak_cpu.png")
        return
    cpu = cpu_log(log_path)
    man = json.loads((RAW / "peak" / session / "manifest.json").read_text())
    times = {(r["job"], r["rep"]): (dt.datetime.fromisoformat(r["start"]), dt.datetime.fromisoformat(r["end"]))
             for r in man["runs"]}
    per = [r for r in csv.DictReader((PROC / "summary.csv").open())
           if r["experiment"] == "peak" and r["session"] == session and r["dir"] == "read"]
    by_job = defaultdict(list)
    for r in per:
        by_job[r["job"]].append(float(r["iops"]))
    pts = {"4 KiB random read": ([], []), "128 KiB sequential read": ([], [])}
    for r in per:
        s, e = times[(r["job"], int(r["rep"]))]
        samples = [v for t, v in cpu if s + dt.timedelta(seconds=5) <= t <= e]
        if not samples:
            continue
        key = "4 KiB random read" if r["rw"] == "randread" else "128 KiB sequential read"
        pts[key][0].append(statistics.mean(samples) * 2.2 / 100)          # GHz, base clock 2.2
        pts[key][1].append(100 * float(r["iops"]) / statistics.mean(by_job[r["job"]]))
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    style(ax, "Random-read IOPS tracks CPU clock; sequential bandwidth does not",
          "each dot = one run; y = IOPS relative to the mean of the same setting; "
          "x = mean CPU clock from typeperf")
    for (label, (x, y)), c in zip(pts.items(), (C1, C2)):
        ax.scatter(x, y, s=40, color=c, edgecolor="white", linewidth=1.5,
                   label=f"{label} (r = {pearson(x, y):.2f})", zorder=3)
    ax.axhline(100, color=MUTED, linewidth=1)
    ax.set_xlabel("Mean CPU clock during run (GHz, ≈ % Processor Performance × 2.2 GHz)", color=INK)
    ax.set_ylabel("IOPS vs. setting mean (%)", color=INK)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "peak_cpu.png")
    for k, (x, y) in pts.items():
        print(f"{k}: n={len(x)} r={pearson(x, y):.2f}")
    print("wrote peak_iops.png, peak_seq.png, peak_cpu.png")


if __name__ == "__main__":
    main()

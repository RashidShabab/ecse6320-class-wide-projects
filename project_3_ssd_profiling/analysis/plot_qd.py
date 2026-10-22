"""Queue-depth sweep figures from results/processed/summary_agg.csv.

  figures/qd_tradeoff.png : throughput vs mean latency, one point per QD (the knee curve)
  figures/qd_littles.png  : Little's Law check, effective outstanding I/O vs requested QD

Usage: python analysis/plot_qd.py [--session SESSION]   (default: latest qd session)
Error bars are +/- 1 std across repetitions.
"""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
AGG = ROOT / "results" / "processed" / "summary_agg.csv"
FIG = ROOT / "figures"
INK, MUTED, GRID, SERIES = "#1f2328", "#59636e", "#d8dee4", "#2a6fdb"


def style(ax):
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", help="qd session folder name (default: latest)")
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(AGG.open()) if r["experiment"] == "qd" and r["dir"] == "read"]
    if not rows:
        raise SystemExit("no qd results; run: ssdbench.py run qd, then ssdbench.py parse")
    session = a.session or max(r["session"] for r in rows)
    rows = sorted((r for r in rows if r["session"] == session), key=lambda r: int(r["iodepth"]))
    nj = rows[0]["numjobs"]
    qd = [int(r["iodepth"]) for r in rows]
    f = lambda k: [float(r[k]) for r in rows]
    kiops, kiops_sd = [v / 1e3 for v in f("iops_mean")], [v / 1e3 for v in f("iops_std")]
    lat, lat_sd = f("lat_mean_us_mean"), f("lat_mean_us_std")
    L, L_sd = f("littles_L_mean"), f("littles_L_std")
    FIG.mkdir(exist_ok=True)
    fixed = f"4 KiB random read, direct I/O, numjobs={nj}, {rows[0]['n']} reps, 64 GiB range"

    # throughput vs latency
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    style(ax)
    ax.errorbar(lat, kiops, xerr=lat_sd, yerr=kiops_sd, color=SERIES, ecolor=SERIES, elinewidth=1,
                capsize=3, linewidth=2, marker="o", markersize=6)
    for x, y, q in zip(lat, kiops, qd):
        ax.annotate(f"QD {q}", (x, y), textcoords="offset points", xytext=(6, -12), fontsize=8, color=INK)
    ax.set_xscale("log")
    ax.set_xlabel("Mean latency (µs, log scale)", color=INK)
    ax.set_ylabel("Throughput (kIOPS)", color=INK)
    ax.set_ylim(bottom=0)
    ax.set_title("Throughput vs latency across queue depth", color=INK, loc="left", fontsize=12, pad=18)
    ax.text(0, 1.01, fixed, transform=ax.transAxes, fontsize=8, color=MUTED, va="bottom")
    fig.tight_layout()
    fig.savefig(FIG / "qd_tradeoff.png")

    # Little's Law
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    style(ax)
    ax.plot(qd, [q * int(nj) for q in qd], color=MUTED, linestyle="--", linewidth=1.5,
            label="Requested outstanding I/O (iodepth × numjobs)")
    ax.errorbar(qd, L, yerr=L_sd, color=SERIES, linewidth=2, marker="o", markersize=6, capsize=3,
                label="Measured L = IOPS × mean latency")
    ax.set_xscale("log", base=2)
    ax.set_yscale("log", base=2)
    ax.set_xticks(qd, [str(q) for q in qd])
    ax.set_yticks(qd, [str(q) for q in qd])
    ax.set_xlabel("Queue depth (iodepth)", color=INK)
    ax.set_ylabel("Outstanding I/Os (log scale)", color=INK)
    ax.set_title("Little's Law check: effective vs requested queue depth", color=INK, loc="left", fontsize=12, pad=18)
    ax.text(0, 1.01, fixed, transform=ax.transAxes, fontsize=8, color=MUTED, va="bottom")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(FIG / "qd_littles.png")
    print("wrote", FIG / "qd_tradeoff.png", "and", FIG / "qd_littles.png", f"(session {session})")


if __name__ == "__main__":
    main()

"""Time series for the 'steady' sustained-write experiment.

  figures/steady.png : write bandwidth (top) and mean completion latency (bottom), 1-second averages

Usage: python analysis/plot_steady.py [--session S]
FIO logs: bandwidth in KiB/s, latency in ns, one line per 1000 ms (log_avg_msec=1000).
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw" / "steady"
FIG = ROOT / "figures"
INK, MUTED, GRID, C1, C2 = "#1f2328", "#59636e", "#d8dee4", "#2a78d6", "#eb6834"
PCIE = 16e9 * 4 * 128 / 130 / 8 / 1e6


def read_log(path, scale):
    out = []
    for line in path.read_text().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and parts[0].isdigit():
            out.append((int(parts[0]) / 1000, int(parts[1]) * scale))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session")
    a = ap.parse_args()
    session = RAW / (a.session or sorted(p.name for p in RAW.iterdir() if p.is_dir())[-1])
    bw = read_log(next(session.glob("*_bw.1.log")), 1024 / 1e6)         # KiB/s -> MB/s
    lat = read_log(next(session.glob("*_clat.1.log")), 1 / 1e3)          # ns -> us
    total = 0.0
    cum = []
    for _, mbps in bw:
        total += mbps / 1000
        cum.append(total)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 6.2), dpi=150, sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})
    for ax in (ax1, ax2):
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(MUTED)
        ax.tick_params(colors=MUTED)
    t, y = zip(*bw)
    ax1.plot(t, y, color=C1, linewidth=1.2)
    ax1.axhline(PCIE, color=MUTED, linestyle="--", linewidth=1.2)
    ax1.text(t[-1], PCIE + 120, f"PCIe Gen4 x4 ≈ {PCIE:,.0f} MB/s", ha="right", fontsize=8, color=MUTED)
    drop = next((i for i, v in enumerate(y) if v < 0.5 * max(y[:3])), None)
    if drop:
        ax1.text(t[drop] + 2, y[drop] + 1000, f"← write cache exhausted after ~{cum[drop - 1]:.0f} GB ({t[drop]:.0f} s)",
                 fontsize=8, color=INK, va="bottom")
    ax1.set_ylim(0, PCIE * 1.12)
    ax1.set_ylabel("Write bandwidth (MB/s)", color=INK)
    ax1.set_title("Sustained sequential write: burst, then steady state with recovery bursts",
                  color=INK, loc="left", fontsize=12, pad=18)
    ax1.text(0, 1.01, f"128 KiB sequential write, QD 32, numjobs 1, direct I/O, 1 s averages, "
                      f"{cum[-1]:.0f} GB written in {t[-1]:.0f} s", transform=ax1.transAxes,
             fontsize=8, color=MUTED, va="bottom")
    lt, ly = zip(*lat)
    ax2.plot(lt, ly, color=C2, linewidth=1.2)
    ax2.set_ylim(bottom=0)
    ax2.set_ylabel("Mean completion\nlatency (µs)", color=INK)
    ax2.set_xlabel("Time (s)", color=INK)
    fig.tight_layout()
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / "steady.png")
    print("wrote steady.png")


if __name__ == "__main__":
    main()

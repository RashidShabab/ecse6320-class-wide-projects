"""Shared plot style and data loading for the Project 2 figures (same look as Project 3)."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
AGG = ROOT / "results" / "processed" / "summary_agg.csv"
FIG = ROOT / "figures"
INK, MUTED, GRID = "#1f2328", "#59636e", "#d8dee4"
# categorical slots in fixed order (validated: CVD and normal-vision separation pass);
# every multi-series plot also differs by marker shape, so color is never the only cue
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
MARKERS = ["o", "s", "^"]
KIB = 1024


def style(ax):
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED)


def new(title, subtitle):
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    style(ax)
    ax.set_title(title, color=INK, loc="left", fontsize=12, pad=18)
    ax.text(0, 1.01, subtitle, transform=ax.transAxes, fontsize=8, color=MUTED, va="bottom")
    return fig, ax


def save(fig, name):
    FIG.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name)
    plt.close(fig)
    print("wrote", FIG / name)


def load(experiment, session=None):
    """Rows of summary_agg.csv for one experiment, latest session unless given."""
    if not AGG.exists():
        raise SystemExit("no summary_agg.csv; run: scripts/membench.py parse")
    rows = [r for r in csv.DictReader(AGG.open()) if r["experiment"] == experiment]
    if not rows:
        return [], None
    session = session or max(r["session"] for r in rows)
    return [r for r in rows if r["session"] == session], session


def f(row, key):
    v = row.get(key, "")
    return float(v) if v not in ("", None) else float("nan")


def size_label(nbytes):
    nbytes = int(float(nbytes))
    for unit, div in (("G", KIB ** 3), ("M", KIB ** 2), ("K", KIB)):
        if nbytes >= div and nbytes % div == 0:
            return f"{nbytes // div}{unit}"
    return f"{nbytes / KIB:.0f}K" if nbytes >= KIB else str(nbytes)


def errs(rows, key):
    """Median with asymmetric min/max bars."""
    med = [f(r, f"{key}_median") for r in rows]
    lo = [m - f(r, f"{key}_min") for m, r in zip(med, rows)]
    hi = [f(r, f"{key}_max") - m for m, r in zip(med, rows)]
    return med, [lo, hi]

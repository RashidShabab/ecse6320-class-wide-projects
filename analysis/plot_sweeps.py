"""Figures for the block-size, read/write-mix, LBA-range and tail-latency experiments.

  figures/bs_bw.png     : MB/s vs block size (random and sequential), with PCIe Gen4 x4 ceiling
  figures/bs_iops.png   : kIOPS vs block size
  figures/bs_lat.png    : mean and p99 latency vs block size (random)
  figures/mix_iops.png  : read + write kIOPS per read/write mix (stacked)
  figures/range_lat.png : mean latency vs LBA range
  figures/tail.png      : p50/p95/p99/p99.9 at each tail QD (log scale)

Usage: python analysis/plot_sweeps.py      (latest session of each experiment)
Error bars: +/- 1 std across repetitions.
"""
import csv
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
AGG = ROOT / "results" / "processed" / "summary_agg.csv"
FIG = ROOT / "figures"
INK, MUTED, GRID = "#1f2328", "#59636e", "#d8dee4"
C1, C2 = "#2a78d6", "#eb6834"
RAMP = ["#9ec5f4", "#5598e7", "#256abf", "#104281"]          # ordinal: p50 -> p99.9
PCIE = 16e9 * 4 * 128 / 130 / 8 / 1e6


def kib(s):
    m = re.match(r"(\d+)([kKmMgG])", str(s))
    return int(m.group(1)) * {"k": 1, "m": 1024, "g": 1024 ** 2}[m.group(2).lower()]


def latest(rows, exp):
    rs = [r for r in rows if r["experiment"] == exp]
    if not rs:
        return []
    session = max(r["session"] for r in rs)
    return [r for r in rs if r["session"] == session]


def sessions(rows, exp):
    """[(suffix, rows)] for every session; untagged session -> '', tagged -> '_<tag>'."""
    out = []
    for s in sorted({r["session"] for r in rows if r["experiment"] == exp}):
        tag = "_" + s[16:] if len(s) > 16 else ""
        out.append((tag, [r for r in rows if r["experiment"] == exp and r["session"] == s]))
    return out


def fig(title, sub):
    f, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED)
    ax.set_title(title, color=INK, loc="left", fontsize=12, pad=18)
    ax.text(0, 1.01, sub, transform=ax.transAxes, fontsize=8, color=MUTED, va="bottom")
    return f, ax


def save(f, name):
    f.tight_layout()
    f.savefig(FIG / name)
    plt.close(f)
    print("wrote", name)


def v(r, k, scale=1):
    return float(r[f"{k}_mean"]) / scale, float(r[f"{k}_std"]) / scale


def main():
    FIG.mkdir(exist_ok=True)
    rows = list(csv.DictReader(AGG.open()))

    # ---------------- block size ----------------
    bs = [r for r in latest(rows, "bs") if r["dir"] == "read"]
    if bs:
        n, qd = bs[0]["n"], bs[0]["iodepth"]
        sub = f"direct I/O, QD {qd}, numjobs 1, 64 GiB range, mean ± std of {n} reps"
        groups = [("randread", "Random read", C1), ("read", "Sequential read", C2)]
        for metric, scale, ylabel, title, name in (
                ("bw_MBps", 1, "Throughput (MB/s)", "Bandwidth grows with block size until the link saturates", "bs_bw.png"),
                ("iops", 1e3, "Throughput (kIOPS)", "IOPS stays flat to 32 KiB, then falls as bandwidth saturates", "bs_iops.png")):
            f, ax = fig(title, sub)
            for rw, label, c in groups:
                rs = sorted([r for r in bs if r["rw"] == rw], key=lambda r: kib(r["bs"]))
                x = [kib(r["bs"]) for r in rs]
                y, e = zip(*[v(r, metric, scale) for r in rs])
                ax.errorbar(x, y, yerr=e, color=c, linewidth=2, marker="o", markersize=6, capsize=3, label=label)
            if metric == "bw_MBps":
                ax.axhline(PCIE, color=MUTED, linestyle="--", linewidth=1.5)
                ax.text(4, PCIE + 80, f"PCIe Gen4 x4 theoretical ≈ {PCIE:,.0f} MB/s", fontsize=8, color=MUTED)
                ax.set_ylim(0, PCIE * 1.12)
            else:
                ax.set_ylim(bottom=0)
            ax.set_xscale("log", base=2)
            ax.set_xticks(x, [f"{k}K" for k in x])
            ax.set_xlabel("Block size (KiB)", color=INK)
            ax.set_ylabel(ylabel, color=INK)
            ax.legend(frameon=False, fontsize=9, labelcolor=INK)
            save(f, name)

        f, ax = fig("Latency rises once each request carries more data", sub + " — random read")
        rs = sorted([r for r in bs if r["rw"] == "randread"], key=lambda r: kib(r["bs"]))
        x = [kib(r["bs"]) for r in rs]
        for k, label, c in (("lat_mean_us", "Mean", C1), ("p99_us", "p99", C2)):
            y, e = zip(*[v(r, k) for r in rs])
            ax.errorbar(x, y, yerr=e, color=c, linewidth=2, marker="o", markersize=6, capsize=3, label=label)
        ax.set_xscale("log", base=2)
        ax.set_xticks(x, [f"{k}K" for k in x])
        ax.set_ylim(bottom=0)
        ax.set_xlabel("Block size (KiB)", color=INK)
        ax.set_ylabel("Latency (µs)", color=INK)
        ax.legend(frameon=False, fontsize=9, labelcolor=INK)
        save(f, "bs_lat.png")

    # ---------------- mix ----------------
    for suffix, mix in sessions(rows, "mix"):
        mixes = sorted({int(r["rwmixread"]) for r in mix}, reverse=True)
        f, ax = fig("Total IOPS across read/write mixes",
                    f"4 KiB random, direct I/O, QD {mix[0]['iodepth']} × numjobs {mix[0]['numjobs']}, mean ± std of {mix[0]['n']} reps")
        xs = range(len(mixes))
        rd = [next((v(r, "iops", 1e3) for r in mix if int(r["rwmixread"]) == m and r["dir"] == "read"), (0, 0)) for m in mixes]
        wr = [next((v(r, "iops", 1e3) for r in mix if int(r["rwmixread"]) == m and r["dir"] == "write"), (0, 0)) for m in mixes]
        ax.bar(xs, [a for a, _ in rd], width=0.55, color=C1, label="Read", edgecolor="white", linewidth=2)
        ax.bar(xs, [a for a, _ in wr], width=0.55, bottom=[a for a, _ in rd], color=C2, label="Write",
               edgecolor="white", linewidth=2)
        tot = [a + b for (a, _), (b, _) in zip(rd, wr)]
        err = [(sa ** 2 + sb ** 2) ** 0.5 for (_, sa), (_, sb) in zip(rd, wr)]
        ax.errorbar(xs, tot, yerr=err, fmt="none", ecolor=INK, capsize=4, linewidth=1)
        top = max(a + b for a, b in zip(tot, err))
        for x, t, e in zip(xs, tot, err):
            ax.text(x + 0.3, t, f"{t:.0f}k", ha="left", va="center", fontsize=9, color=INK)
        ax.set_xticks(list(xs), [f"{m}/{100 - m}" for m in mixes])
        ax.set_xlabel("Read / write mix (%)", color=INK)
        ax.set_ylabel("Throughput (kIOPS)", color=INK)
        ax.set_ylim(0, top * 1.08)
        ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper right")
        save(f, f"mix_iops{suffix}.png")

    # ---------------- range ----------------
    for suffix, rng in sessions(rows, "range"):
        rng = [r for r in rng if r["dir"] == "read"]
        rs = sorted(rng, key=lambda r: kib(r["size"]))
        x = [kib(r["size"]) / 1024 ** 2 for r in rs]
        f, ax = fig("Latency is flat across the tested LBA ranges (1-64 GiB)",
                    f"4 KiB random read, direct I/O, QD {rs[0]['iodepth']}, numjobs 1, mean ± std of {rs[0]['n']} reps")
        for k, label, c in (("lat_mean_us", "Mean", C1), ("p99_us", "p99", C2)):
            y, e = zip(*[v(r, k) for r in rs])
            ax.errorbar(x, y, yerr=e, color=c, linewidth=2, marker="o", markersize=6, capsize=3, label=label)
        ax.set_xscale("log", base=2)
        ax.set_xticks(x, [f"{int(g)} GiB" for g in x])
        ax.set_ylim(bottom=0)
        ax.set_xlabel("LBA range (working set)", color=INK)
        ax.set_ylabel("Latency (µs)", color=INK)
        ax.legend(frameon=False, fontsize=9, labelcolor=INK)
        save(f, f"range_lat{suffix}.png")

    # ---------------- tail ----------------
    tail = sorted([r for r in latest(rows, "tail") if r["dir"] == "read"], key=lambda r: int(r["iodepth"]))
    if tail:
        f, ax = fig("Tail latency below, at and past the knee",
                    f"4 KiB random read, direct I/O, numjobs 1, 120 s runs, mean ± std of {tail[0]['n']} reps")
        pcts = (("p50_us", "p50"), ("p95_us", "p95"), ("p99_us", "p99"), ("p999_us", "p99.9"))
        w = 0.19
        for i, ((k, label), c) in enumerate(zip(pcts, RAMP)):
            xs = [j + (i - 1.5) * w for j in range(len(tail))]
            ys, es = zip(*[v(r, k) for r in tail])
            ax.bar(xs, ys, width=w - 0.02, color=c, label=label, yerr=es, ecolor=INK, capsize=2,
                   error_kw={"linewidth": 0.8})
        ax.set_yscale("log")
        ax.set_xticks(range(len(tail)), [f"QD {r['iodepth']}\n{float(r['iops_mean'])/1e3:.0f}k IOPS" for r in tail])
        ax.set_ylabel("Latency (µs, log scale)", color=INK)
        ax.legend(frameon=False, fontsize=9, labelcolor=INK, ncol=4, loc="upper left")
        ax.set_ylim(top=ax.get_ylim()[1] * 2.5)
        save(f, "tail.png")


if __name__ == "__main__":
    main()

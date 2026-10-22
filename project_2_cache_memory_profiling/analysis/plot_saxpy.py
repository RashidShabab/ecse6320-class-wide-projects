"""Cache-miss impact on SAXPY (y = a*x + y).

  figures/saxpy_runtime.png    time per element vs footprint, sequential vs random order
  figures/saxpy_misses.png     time per element vs L2 misses per element (correlation)
  results/processed/saxpy.md   table + Pearson correlation of time with L1D and L2 misses

Note: the column llc_miss_per_elem comes from perf's generic `cache-misses` event, which
Linux maps to an L2-miss event on AMD Zen (true L3 misses need uncore counters / root).
The data confirm it: the count rises past L2's 1 MiB, not L3's 32 MiB.

Usage: python3 analysis/plot_saxpy.py [--session S]   (default: latest saxpy session)
Points are medians; bars span min-max across repetitions.
"""
import argparse
import math

from plotstyle import BLUE, INK, KIB, MARKERS, MUTED, ORANGE, ROOT, errs, f, load, new, save, size_label

CAPACITY = [(48 * KIB, "L1d"), (KIB ** 2, "L2"), (32 * KIB ** 2, "L3 (1 CCD)")]
LABELS = {"seq": "Sequential (vectorized)", "rand": "Random index order"}
COLORS = {"seq": BLUE, "rand": ORANGE}


def pearson(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x == x and y == y]
    if len(pts) < 3:
        return float("nan")
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    syy = sum((y - my) ** 2 for _, y in pts)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session")
    a = ap.parse_args()
    rows, session = load("saxpy", a.session)
    if not rows:
        raise SystemExit("no saxpy results; run: membench.py run saxpy, then membench.py parse")
    by = {p: sorted((r for r in rows if r["pattern"] == p), key=lambda r: float(r["size_bytes"]))
          for p in ("seq", "rand")}
    sub = f"SAXPY y = a·x + y (float), CPU {rows[0]['cpu']}, 2 MiB pages, {rows[0]['n']} reps"

    fig, ax = new("SAXPY time per element vs footprint", sub + " (median, min-max bars)")
    for i, p in enumerate(("seq", "rand")):
        rs = by[p]
        x = [float(r["size_bytes"]) for r in rs]
        y, e = errs(rs, "ns_per_elem")
        ax.errorbar(x, y, yerr=e, color=COLORS[p], marker=MARKERS[i], markersize=6, linewidth=2, capsize=2,
                    label=LABELS[p])
    for cap, label in CAPACITY:
        ax.axvline(cap, color=MUTED, linestyle="--", linewidth=1)
        ax.text(cap * 1.08, 0.97, label, color=MUTED, fontsize=8, va="top", transform=ax.get_xaxis_transform())
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    xs = sorted({float(r["size_bytes"]) for r in rows})
    ax.set_xticks(xs[::2], [size_label(v) for v in xs[::2]])
    ax.set_xlabel("Footprint of x + y (log scale)", color=INK)
    ax.set_ylabel("Time per element (ns, log scale)", color=INK)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left", bbox_to_anchor=(0, 0.9))
    save(fig, "saxpy_runtime.png")

    fig, ax = new("SAXPY time per element vs L2 misses", sub + "; L2 misses = perf generic cache-misses on AMD")
    lines, corr = [], {}
    for i, p in enumerate(("seq", "rand")):
        rs = by[p]
        llc = [f(r, "llc_miss_per_elem_median") for r in rs]
        l1 = [f(r, "l1d_miss_per_elem_median") for r in rs]
        ns = [f(r, "ns_per_elem_median") for r in rs]
        corr[p] = (pearson(l1, ns), pearson(llc, ns))
        if any(v == v for v in llc):
            ax.plot(llc, ns, color=COLORS[p], marker=MARKERS[i], markersize=7, linewidth=0, label=LABELS[p])
            for xv, yv, r in zip(llc, ns, rs):
                ax.annotate(size_label(r["size_bytes"]), (xv, yv), textcoords="offset points", xytext=(5, 3),
                            fontsize=7, color=MUTED)
        for r in rs:
            lines.append(f"| {p} | {size_label(r['size_bytes'])} | {f(r, 'ns_per_elem_median'):.3f} "
                         f"| {f(r, 'cycles_per_elem_median'):.2f} | {f(r, 'ipc_median'):.2f} "
                         f"| {f(r, 'l1d_miss_per_elem_median'):.4f} | {f(r, 'llc_miss_per_elem_median'):.4f} "
                         f"| {f(r, 'dtlb_miss_per_elem_median'):.4f} | {f(r, 'gb_per_s_median'):.1f} |")
    ax.set_xlabel("L2 misses per element", color=INK)
    ax.set_ylabel("Time per element (ns, log scale)", color=INK)
    ax.set_yscale("log")
    ax.set_xlim(left=0)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    save(fig, "saxpy_misses.png")

    out = ROOT / "results" / "processed" / "saxpy.md"
    text = [f"SAXPY cache-miss impact (session {session}; medians of {rows[0]['n']} reps)", "",
            "| Order | Footprint | ns/elem | cycles/elem | IPC | L1D miss/elem | L2 miss/elem* | dTLB miss/elem | GB/s (12 B/elem) |",
            "|---|---|---|---|---|---|---|---|---|", *lines, "",
            "*perf generic `cache-misses`, which counts L2 misses on AMD Zen.", "",
            "Pearson correlation of time per element with misses per element (across footprints):", ""]
    for p, (r1, r2) in corr.items():
        text.append(f"- {LABELS[p]}: L1D r = {r1:.3f}, L2 r = {r2:.3f}")
    out.write_text("\n".join(text) + "\n")
    print("\n".join(text))
    print("wrote", out)


if __name__ == "__main__":
    main()

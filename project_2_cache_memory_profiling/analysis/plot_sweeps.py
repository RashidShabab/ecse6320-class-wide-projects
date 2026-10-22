"""Pattern/stride, read/write mix, TLB and pitfall figures.

  figures/pattern_latency.png    seq vs rand latency at 64/256/1024 B stride (1 GiB)
  figures/pattern_bw.png         seq vs rand bandwidth at the same strides
  figures/rw_bw.png              bandwidth vs read share, 1 and 16 threads
  figures/tlb_latency.png        latency per access, 4 KiB vs 2 MiB pages, one access per page
  figures/tlb_misses.png         dTLB misses per access for the same runs
  results/processed/sanity.md    pitfall-demo table

Usage: python3 analysis/plot_sweeps.py   (latest session of each experiment)
Bars/points are medians; error bars span min-max across repetitions.
"""
from plotstyle import BLUE, INK, MARKERS, MUTED, ORANGE, ROOT, errs, f, load, new, save, size_label

COLORS = [BLUE, ORANGE]


def grouped_bars(ax, groups, series, values, err, labels):
    width = 0.38
    for i, (s, color) in enumerate(zip(series, COLORS)):
        xs = [g + (i - 0.5) * width for g in range(len(groups))]
        bars = ax.bar(xs, values[s], width - 0.04, yerr=err[s], color=color, ecolor=INK, capsize=3,
                      label=labels[s])
        for b, v in zip(bars, values[s]):
            ax.annotate(f"{v:.3g}", (b.get_x() + b.get_width() / 2, b.get_height()),
                        textcoords="offset points", xytext=(0, 3), ha="center", fontsize=8, color=INK)
    ax.set_xticks(range(len(groups)), groups)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)


def pattern():
    rows, session = load("pattern")
    if not rows:
        return print("no pattern results")
    by = {r["point"]: r for r in rows}
    strides = sorted({int(r["stride"]) for r in rows})
    groups = [f"{s} B" for s in strides]
    labels = {"seq": "Sequential", "rand": "Random"}
    for kind, key, ylabel, title, name in [
            ("lat", "ns_per_load", "Latency per load (ns)", "Pointer-chase latency: pattern and stride",
             "pattern_latency.png"),
            ("bw", "gb_per_s", "Bandwidth (GB/s)", "Streaming read bandwidth: pattern and stride",
             "pattern_bw.png")]:
        vals, err = {}, {}
        for p in ("seq", "rand"):
            rs = [by[f"{kind}_{p}_s{s}"] for s in strides if f"{kind}_{p}_s{s}" in by]
            vals[p], err[p] = errs(rs, key)
        r0 = by[f"{kind}_seq_s{strides[0]}"]
        tool = "pchase, 1 chain" if kind == "lat" else "bwbench, 1 thread, 100 % reads, 64 B touched per access"
        fig, ax = new(title, f"{size_label(r0['size_bytes'])} working set (DRAM), {tool}, CPU {r0.get('cpus') or r0.get('cpu')}, "
                             f"{r0['n']} reps")
        grouped_bars(ax, groups, ["seq", "rand"], vals, err, labels)
        ax.set_xlabel("Stride between accesses", color=INK)
        ax.set_ylabel(ylabel, color=INK)
        ax.set_ylim(bottom=0)
        save(fig, name)


def rw():
    rows, session = load("rw")
    if not rows:
        return print("no rw results")
    fig, ax = new("Bandwidth vs read/write mix",
                  f"bwbench, sequential, 64 B stride, {size_label(rows[0]['size_bytes'])}, {rows[0]['n']} reps; "
                  "written bytes counted once (DRAM moves them ~2x)")
    for i, t in enumerate(sorted({int(r["threads"]) for r in rows})):
        rs = sorted((r for r in rows if int(r["threads"]) == t), key=lambda r: -int(r["read_pct"]))
        x = [int(r["read_pct"]) for r in rs]
        y, e = errs(rs, "gb_per_s")
        ax.errorbar(x, y, yerr=e, color=COLORS[i % 2], marker=MARKERS[i % 3], markersize=7, linewidth=2,
                    capsize=3, label=f"{t} thread{'s' if t > 1 else ''}")
        ax.annotate(f"{y[0]:.1f}", (x[0], y[0]), textcoords="offset points", xytext=(6, 4), fontsize=8, color=INK)
    ax.set_xticks([100, 70, 50, 0], ["100 % read", "70/30", "50/50", "100 % write"])
    ax.invert_xaxis()
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Read share", color=INK)
    ax.set_ylabel("Bandwidth (GB/s)", color=INK)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    save(fig, "rw_bw.png")


def tlb():
    rows, session = load("tlb")
    if not rows:
        return print("no tlb results")
    labels = {"4k": "4 KiB pages", "huge": "2 MiB pages"}
    for key, ylabel, title, name in [
            ("ns_per_load", "Latency per access (ns)", "TLB impact: latency, one access per 4 KiB page",
             "tlb_latency.png"),
            ("dtlb_miss_per_load", "dTLB misses per access", "TLB impact: dTLB misses per access",
             "tlb_misses.png")]:
        fig, ax = new(title, f"Random pointer chase, 4096 B stride (every access a new 4 KiB page), CPU {rows[0]['cpu']}, "
                             f"{rows[0]['n']} reps")
        for i, pg in enumerate(("4k", "huge")):
            rs = sorted((r for r in rows if r["pages"] == pg), key=lambda r: float(r["size_bytes"]))
            if not rs:
                continue
            x = [float(r["size_bytes"]) for r in rs]
            y, e = errs(rs, key)
            ax.errorbar(x, y, yerr=e, color=COLORS[i], marker=MARKERS[i], markersize=7, linewidth=2,
                        capsize=3, label=labels[pg])
        ax.set_xscale("log", base=2)
        xs = sorted({float(r["size_bytes"]) for r in rows})
        ax.set_xticks(xs, [size_label(v) for v in xs])
        ax.set_ylim(bottom=0)
        ax.set_xlabel("Region size (log scale)", color=INK)
        ax.set_ylabel(ylabel, color=INK)
        ax.legend(frameon=False, fontsize=9, labelcolor=INK)
        save(fig, name)


def sanity():
    rows, session = load("sanity")
    if not rows:
        return print("no sanity results")
    lines = [f"Pitfall demos (session {session}; median of {rows[0]['n']} reps)", "",
             "| Point | Pages requested | AnonHugePages (kB) | ns/access | cycles/access | dTLB misses/access |",
             "|---|---|---|---|---|---|"]
    raw = {r["point"]: r for r in rows}
    for r in sorted(rows, key=lambda r: r["point"]):
        lines.append(f"| {r['point']} | {r['pages']} | {_huge_kb(session, r['point'])} "
                     f"| {f(r, 'ns_per_load_median'):.2f} | {f(r, 'cycles_per_load_median'):.1f} "
                     f"| {f(r, 'dtlb_miss_per_load_median'):.3f} |")
    out = ROOT / "results" / "processed" / "sanity.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("wrote", out)
    return raw


def _huge_kb(session, point):
    path = ROOT / "results" / "raw" / "sanity" / session / f"{point}.csv"
    try:
        last = path.read_text().strip().splitlines()[-1]
        return last.split(",")[-1]
    except (OSError, IndexError):
        return "?"


def main():
    pattern()
    rw()
    tlb()
    sanity()


if __name__ == "__main__":
    main()

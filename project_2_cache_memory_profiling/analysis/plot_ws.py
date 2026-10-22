"""Working-set sweep and zero-queue baselines.

  figures/ws_latency.png          latency (ns) vs working-set size: the staircase
  figures/ws_cycles.png           same in core cycles (clock-independent for caches)
  results/processed/baseline.md   zero-queue baseline table (L1/L2/L3/DRAM)

Usage: python3 analysis/plot_ws.py [--ws-session S] [--baseline-session S]
Points are medians; bars span min-max across repetitions.
"""
import argparse

from plotstyle import BLUE, INK, KIB, MUTED, ROOT, errs, f, load, new, save, size_label

CAPACITY = [(48 * KIB, "L1d 48 KiB"), (KIB ** 2, "L2 1 MiB"), (32 * KIB ** 2, "L3 32 MiB (1 CCD)")]


def staircase(rows, key, ylabel, title, name, logy):
    x = [int(float(r["size_bytes"])) for r in rows]
    y, e = errs(rows, key)
    if not any(v == v for v in y):
        return print(f"no {key} values (counters unavailable?); skipping {name}")
    fig, ax = new(title, f"Random pointer chase, 1 chain, 64 B stride, 2 MiB pages, CPU {rows[0]['cpu']}, "
                         f"{rows[0]['n']} reps (median, min-max bars)")
    ax.errorbar(x, y, yerr=e, color=BLUE, ecolor=BLUE, elinewidth=1, capsize=2, linewidth=2,
                marker="o", markersize=5)
    ax.set_xscale("log", base=2)
    if logy:
        ax.set_yscale("log")
    ticks = [4 * KIB * 4 ** i for i in range(9) if 4 * KIB * 4 ** i <= max(x)]
    ax.set_xticks(ticks, [size_label(t) for t in ticks])
    for cap, label in CAPACITY:
        ax.axvline(cap, color=MUTED, linestyle="--", linewidth=1)
        ax.text(cap * 1.08, 0.03, label, color=MUTED, fontsize=8, va="bottom",
                transform=ax.get_xaxis_transform())
    ax.set_xlabel("Working-set size (log scale)", color=INK)
    ax.set_ylabel(ylabel, color=INK)
    save(fig, name)


def baseline_table(session):
    rows, session = load("baseline", session)
    if not rows:
        print("no baseline results; skipping baseline.md")
        return
    order = {"L1": 0, "L2": 1, "L3": 2, "DRAM": 3}
    rows.sort(key=lambda r: order.get(r["point"].split("_")[0], 9))
    lines = [f"Zero-queue baselines (session {session}; median of {rows[0]['n']} reps, min-max in brackets)", "",
             "| Level | Working set | Latency (ns) | Latency (cycles) | Clock (GHz) |",
             "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['point'].split('_')[0]} | {size_label(r['size_bytes'])} "
                     f"| {f(r, 'ns_per_load_median'):.2f} [{f(r, 'ns_per_load_min'):.2f}-{f(r, 'ns_per_load_max'):.2f}] "
                     f"| {f(r, 'cycles_per_load_median'):.1f} [{f(r, 'cycles_per_load_min'):.1f}-{f(r, 'cycles_per_load_max'):.1f}] "
                     f"| {f(r, 'eff_ghz_median'):.2f} |")
    out = ROOT / "results" / "processed" / "baseline.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("wrote", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws-session")
    ap.add_argument("--baseline-session")
    a = ap.parse_args()
    rows, session = load("ws", a.ws_session)
    if rows:
        rows.sort(key=lambda r: int(float(r["size_bytes"])))
        staircase(rows, "ns_per_load", "Latency per load (ns, log scale)",
                  "Load latency vs working-set size", "ws_latency.png", True)
        staircase(rows, "cycles_per_load", "Latency per load (core cycles, log scale)",
                  "Load latency in core cycles vs working-set size", "ws_cycles.png", True)
    else:
        print("no ws results; skipping staircase")
    baseline_table(a.baseline_session)


if __name__ == "__main__":
    main()

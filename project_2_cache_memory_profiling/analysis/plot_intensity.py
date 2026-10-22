"""Intensity sweep (throughput vs latency, the knee) and Little's Law.

  figures/mlp_tradeoff.png   1 thread, k = 1..32 independent chains: bandwidth vs per-load latency
  figures/mlp_littles.png    Little's Law: measured outstanding misses (bandwidth x latency / 64 B) vs k
  figures/loaded_latency.png latency of one chain vs background bandwidth from 0..14 other cores

Usage: python3 analysis/plot_intensity.py   (latest session of each experiment)
Points are medians; bars span min-max across repetitions.
"""
from plotstyle import BLUE, INK, MUTED, ORANGE, errs, f, load, new, save, size_label


def mlp():
    rows, session = load("mlp")
    if not rows:
        return print("no mlp results")
    rows.sort(key=lambda r: int(r["chains"]))
    k = [int(r["chains"]) for r in rows]
    lat, lat_e = errs(rows, "lat_ns_per_chain")
    bw = [f(r, "mb_per_s_median") / 1000 for r in rows]
    bw_e = [[b - f(r, "mb_per_s_min") / 1000 for b, r in zip(bw, rows)],
            [f(r, "mb_per_s_max") / 1000 - b for b, r in zip(bw, rows)]]
    sub = (f"1 thread on CPU {rows[0]['cpu']}, k independent random chains, "
           f"{size_label(rows[0]['size_bytes'])} working set, {rows[0]['n']} reps")

    fig, ax = new("Throughput vs latency as loads in flight grow", sub)
    ax.errorbar(lat, bw, xerr=lat_e, yerr=bw_e, color=BLUE, ecolor=BLUE, elinewidth=1, capsize=3,
                linewidth=2, marker="o", markersize=6)
    for x, y, q in zip(lat, bw, k):
        ax.annotate(f"k={q}", (x, y), textcoords="offset points", xytext=(6, -12), fontsize=8, color=INK)
    ax.set_xlabel("Latency seen by each load (ns)", color=INK)
    ax.set_ylabel("Bandwidth (GB/s, 64 B per load)", color=INK)
    ax.set_ylim(bottom=0)
    save(fig, "mlp_tradeoff.png")

    # Little's Law: L = throughput (lines/ns) x latency (ns)
    L = [b * 1e9 / 64 * l * 1e-9 for b, l in zip(bw, lat)]
    fig, ax = new("Little's Law check: outstanding misses vs chains", sub)
    ax.plot(k, k, color=MUTED, linestyle="--", linewidth=1.5, label="Ideal: every chain has a miss in flight")
    ax.plot(k, L, color=BLUE, linewidth=2, marker="o", markersize=6,
            label="Measured L = bandwidth × latency / 64 B")
    ax.set_xlabel("Independent chains k", color=INK)
    ax.set_ylabel("Outstanding misses", color=INK)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    save(fig, "mlp_littles.png")


def loaded():
    rows, session = load("loaded")
    if not rows:
        return print("no loaded results")
    rows.sort(key=lambda r: f(r, "bg_gb_per_s_median") if r.get("bg_gb_per_s_median") else 0)
    x = [f(r, "bg_gb_per_s_median") for r in rows]
    y, e = errs(rows, "ns_per_load")
    n = [int(float(r.get("load_threads") or 0)) for r in rows]
    fig, ax = new("Loaded latency: one chain while other cores stream",
                  f"Probe: pchase 1 chain, {size_label(rows[0]['size_bytes'])}, CPU {rows[0]['cpu']}; "
                  f"load: bwbench sequential reads on 0-14 other cores; {rows[0]['n']} reps")
    ax.errorbar(x, y, yerr=e, color=ORANGE, ecolor=ORANGE, elinewidth=1, capsize=3, linewidth=2,
                marker="s", markersize=6)
    for xi, yi, t in zip(x, y, n):
        ax.annotate(f"{t} cores", (xi, yi), textcoords="offset points", xytext=(6, -12), fontsize=8, color=INK)
    ax.set_xlabel("Background bandwidth (GB/s)", color=INK)
    ax.set_ylabel("Probe latency (ns)", color=INK)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    save(fig, "loaded_latency.png")


def main():
    mlp()
    loaded()


if __name__ == "__main__":
    main()

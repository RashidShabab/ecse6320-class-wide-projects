"""Parse every benchmark CSV under results/raw into CSV summaries.

Run from the project folder:  python3 analysis/parse_results.py   (or: scripts/membench.py parse)

Inputs   results/raw/<experiment>/<session>/<point>.csv       (pchase or bwbench output)
         results/raw/<experiment>/<session>/<point>_load.csv  ('loaded' background bandwidth)
Outputs  results/processed/summary.csv      one row per repetition
         results/processed/summary_agg.csv  n, median, mean, std, min, max per point

For 'loaded' points, bg_gb_per_s is the median background bandwidth of the
bwbench repetitions that ran while the latency probe was measuring.
"""
import csv
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw"
OUT = ROOT / "results" / "processed"
KEYS = ["size_bytes", "stride", "pattern", "chains", "pages", "cpu", "threads", "read_pct", "cpus", "load_threads"]
METRICS = ["ns_per_load", "cycles_per_load", "lat_ns_per_chain", "eff_ghz", "mb_per_s",
           "l1d_miss_per_load", "dtlb_miss_per_load", "gb_per_s", "bg_gb_per_s"]


def read_csv(path):
    try:
        lines = [l for l in path.read_text().splitlines() if l and not l.startswith("#")]
    except OSError:
        return []
    if len(lines) < 2:
        return []
    return list(csv.DictReader(lines))


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x  # drop NaN


def parse():
    rows = []
    for path in sorted(RAW.glob("*/*/*.csv")):
        if path.name.endswith(("_load.csv", "_perf.csv")):
            continue
        exp, session, point = path.parent.parent.name, path.parent.name, path.stem
        extra = {}
        load = read_csv(path.with_name(point + "_load.csv"))
        if load:
            gb = sorted(float(r["gb_per_s"]) for r in load)
            extra = {"bg_gb_per_s": gb[len(gb) // 2], "load_threads": load[0]["threads"]}
        elif exp == "loaded":
            extra = {"bg_gb_per_s": 0.0, "load_threads": 0}
        for r in read_csv(path):
            rows.append({"experiment": exp, "session": session, "point": point, **r, **extra})
    return rows


def aggregate(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["experiment"], r["session"], r["point"])].append(r)
    agg = []
    for (exp, session, point), rs in groups.items():
        out = {"experiment": exp, "session": session, "point": point, "n": len(rs)}
        for k in KEYS:
            if k in rs[0]:
                out[k] = rs[0][k]
        for m in METRICS:
            vals = [v for v in (num(r.get(m)) for r in rs) if v is not None]
            if not vals:
                continue
            out[f"{m}_median"] = statistics.median(vals)
            out[f"{m}_mean"] = statistics.fmean(vals)
            out[f"{m}_std"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
            out[f"{m}_min"] = min(vals)
            out[f"{m}_max"] = max(vals)
        agg.append(out)
    return agg


def write(path, rows):
    cols = []
    for r in rows:
        cols += [k for k in r if k not in cols]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main():
    rows = parse()
    if not rows:
        raise SystemExit(f"no results found under {RAW}")
    OUT.mkdir(parents=True, exist_ok=True)
    agg = aggregate(rows)
    write(OUT / "summary.csv", rows)
    write(OUT / "summary_agg.csv", agg)
    print(f"wrote {OUT / 'summary.csv'} ({len(rows)} rows) and {OUT / 'summary_agg.csv'} ({len(agg)} points)")


if __name__ == "__main__":
    main()

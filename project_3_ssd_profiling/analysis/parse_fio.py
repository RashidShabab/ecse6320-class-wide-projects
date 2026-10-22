"""Parse every FIO JSON result under results/raw into CSV summaries.

Run from the repo root:  python3 analysis/parse_fio.py   (or: scripts/ssdbench.py parse)

Outputs
  results/processed/summary.csv      one row per (run, job, direction)
  results/processed/summary_agg.csv  mean and std across repetitions (for error bars)

Latency columns are microseconds of total latency (submission + completion),
because the job files set lat_percentiles=1. littles_L = IOPS x mean latency,
i.e. the effective number of outstanding I/Os, to compare with iodepth x numjobs.
"""
import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw"
OUT = ROOT / "results" / "processed"
PCTS = {"p50_us": "50.000000", "p95_us": "95.000000", "p99_us": "99.000000", "p999_us": "99.900000"}
METRICS = ["iops", "bw_MBps", "lat_mean_us", *PCTS, "littles_L"]


def load(path):
    text = path.read_text(errors="replace")
    return json.loads(text[text.index("{"):])  # skip warning lines fio may print first


def locate(path):
    """experiment, session, rep from either layout:
    results/raw/<exp>/<session>/<job>_r<k>.json   (ssdbench.py)
    results/raw/<exp>_<YYYYmmdd_HHMMSS>_r<k>.json (run_job.ps1)"""
    rel = path.relative_to(RAW).parts
    rep = re.search(r"_r(\d+)\.json$", path.name)
    rep = int(rep.group(1)) if rep else 1
    if len(rel) >= 3:
        return rel[0], rel[1], rep
    m = re.match(r"(.+)_(\d{8}_\d{6})_r\d+\.json", path.name)
    return (m.group(1), m.group(2), rep) if m else (path.stem, "", rep)


def parse():
    rows = []
    for path in sorted(RAW.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            data = load(path)
        except (ValueError, OSError) as e:
            print(f"skip {path}: {e}")
            continue
        exp, session, rep = locate(path)
        glob_opts = data.get("global options", {})
        for job in data.get("jobs", []):
            opts = {**glob_opts, **job.get("job options", {})}
            for d in ("read", "write"):
                s = job[d]
                if s.get("total_ios", 0) == 0:
                    continue
                lat = s.get("lat_ns", {})
                pct = lat.get("percentile") or s.get("clat_ns", {}).get("percentile", {})
                lat_mean_us = lat.get("mean", 0) / 1e3
                row = {
                    "experiment": exp, "session": session, "job": job["jobname"], "rep": rep, "dir": d,
                    "rw": opts.get("rw"), "bs": opts.get("bs"),
                    "iodepth": int(opts.get("iodepth", 1)), "numjobs": int(opts.get("numjobs", 1)),
                    "rwmixread": opts.get("rwmixread", ""), "size": opts.get("size", ""),
                    "direct": opts.get("direct", ""),
                    "iops": round(s["iops"], 1),
                    "bw_MBps": round(s["bw_bytes"] / 1e6, 1),
                    "lat_mean_us": round(lat_mean_us, 2),
                }
                for col, key in PCTS.items():
                    row[col] = round(pct.get(key, 0) / 1e3, 2)
                row["littles_L"] = round(s["iops"] * lat_mean_us / 1e6, 2)
                row["cpu_usr"] = round(job.get("usr_cpu", 0), 1)
                row["cpu_sys"] = round(job.get("sys_cpu", 0), 1)
                row["file"] = str(path.relative_to(RAW))
                rows.append(row)
    return rows


def aggregate(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["experiment"], r["session"], r["job"], r["dir"])].append(r)
    out = []
    for (exp, session, job, d), rs in groups.items():
        first = rs[0]
        a = {"experiment": exp, "session": session, "job": job, "dir": d, "n": len(rs),
             **{k: first[k] for k in ("rw", "bs", "iodepth", "numjobs", "rwmixread", "size", "direct")}}
        for m in METRICS:
            vals = [r[m] for r in rs]
            a[f"{m}_mean"] = round(statistics.mean(vals), 2)
            a[f"{m}_std"] = round(statistics.stdev(vals), 2) if len(vals) > 1 else 0.0
        out.append(a)
    return out


def write(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    rows = parse()
    if not rows:
        print("no results found in", RAW)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "summary.csv", rows)
    agg = aggregate(rows)
    write(OUT / "summary_agg.csv", agg)
    print(f"{len(rows)} rows -> {OUT / 'summary.csv'}")
    print(f"{len(agg)} groups -> {OUT / 'summary_agg.csv'}")


if __name__ == "__main__":
    main()

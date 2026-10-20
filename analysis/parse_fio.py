"""Parse every FIO JSON file in results/raw into results/processed/summary.csv.

Run from the repo root (in WSL):  python3 analysis/parse_fio.py
One row per (file, job, direction). Latency columns are in microseconds and
use total latency (submission + completion), because the job files set
lat_percentiles=1.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw"
OUT = ROOT / "results" / "processed" / "summary.csv"
PCTS = ["50.000000", "95.000000", "99.000000", "99.900000"]


def load(path):
    text = path.read_text(errors="replace")
    return json.loads(text[text.index("{"):])  # skip any warning lines fio prints first


def main():
    rows = []
    for path in sorted(RAW.glob("*.json")):
        m = re.match(r"(.+)_(\d{8}_\d{6})_r(\d+)\.json", path.name)
        data = load(path)
        glob_opts = data.get("global options", {})
        for job in data["jobs"]:
            opts = {**glob_opts, **job.get("job options", {})}
            for d in ("read", "write"):
                s = job[d]
                if s.get("total_ios", 0) == 0:
                    continue
                lat = s.get("lat_ns", {})
                pct = lat.get("percentile") or s.get("clat_ns", {}).get("percentile", {})
                rows.append({
                    "file": path.name,
                    "experiment": m.group(1) if m else path.stem,
                    "rep": int(m.group(3)) if m else 1,
                    "job": job["jobname"],
                    "dir": d,
                    "rw": opts.get("rw"),
                    "bs": opts.get("bs"),
                    "iodepth": int(opts.get("iodepth", 1)),
                    "numjobs": int(opts.get("numjobs", 1)),
                    "direct": opts.get("direct"),
                    "iops": round(s["iops"], 1),
                    "bw_MBps": round(s["bw_bytes"] / 1e6, 1),
                    "lat_mean_us": round(lat.get("mean", 0) / 1e3, 2),
                    "p50_us": round(pct.get(PCTS[0], 0) / 1e3, 2),
                    "p95_us": round(pct.get(PCTS[1], 0) / 1e3, 2),
                    "p99_us": round(pct.get(PCTS[2], 0) / 1e3, 2),
                    "p999_us": round(pct.get(PCTS[3], 0) / 1e3, 2),
                    "cpu_usr": round(job.get("usr_cpu", 0), 1),
                    "cpu_sys": round(job.get("sys_cpu", 0), 1),
                })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with OUT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"{len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()

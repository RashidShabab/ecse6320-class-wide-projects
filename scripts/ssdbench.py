#!/usr/bin/env python3
"""
ssdbench - run the ECSE 4320/6320 Project 3 FIO experiment matrix.

Every run generates a FIO job file, executes it, and saves the job file, the
JSON result and a manifest (knobs, fio version, timestamps) under
results/raw/<experiment>/<session>/ so each result can be reproduced exactly.

Works from:
  * WSL      - calls the Windows fio.exe, so I/O still runs natively on Windows
  * Windows  - native Python + fio on PATH
  * Linux    - native fio (use --ioengine libaio or io_uring)
"""
import argparse
import datetime as dt
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PCT_LIST = "50:95:99:99.9"
SIZE_UNITS = {"k": 2**10, "m": 2**20, "g": 2**30, "t": 2**40}


# --------------------------------------------------------------------------- #
# Platform helpers
# --------------------------------------------------------------------------- #
def in_wsl():
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def windows_target():
    """True when fio itself runs on Windows (native Windows or fio.exe via WSL)."""
    return os.name == "nt" or in_wsl()


def find_fio(user_path):
    if user_path:
        return user_path
    names = ["fio.exe", "fio"] if in_wsl() else ["fio"]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    if in_wsl() and Path("/mnt/c/Program Files/fio/fio.exe").exists():
        return "/mnt/c/Program Files/fio/fio.exe"
    sys.exit("ERROR: fio not found. Pass --fio PATH.")


def local_path(p):
    """Windows path -> path this Python can check (translates C:\\... in WSL)."""
    if in_wsl() and len(p) > 2 and p[1] == ":":
        return Path("/mnt/" + p[0].lower() + p[2:].replace("\\", "/"))
    return Path(p)


def fio_filename(p):
    """FIO treats ':' as a file separator, so escape it on Windows."""
    return p.replace(":", "\\:") if windows_target() else p


def parse_size(s):
    s = str(s).strip().lower()
    for suffix in ("ib", "b"):
        if s.endswith(suffix) and len(s) > len(suffix) and not s[:-len(suffix)].isdigit():
            s = s[:-len(suffix)]
    if s and s[-1] in SIZE_UNITS:
        return int(float(s[:-1]) * SIZE_UNITS[s[-1]])
    return int(s)


def csv_list(cast=str):
    def f(text):
        return [cast(x.strip()) for x in text.split(",") if x.strip()]
    return f


# --------------------------------------------------------------------------- #
# Experiment definitions
# --------------------------------------------------------------------------- #
def common_opts(a):
    o = {
        "ioengine": a.ioengine,
        "direct": 1,
        "filename": fio_filename(a.file),
        "size": a.size,
        "time_based": 1,
        "runtime": a.runtime,
        "ramp_time": a.ramp,
        "randrepeat": 0,
        "group_reporting": 1,
        "lat_percentiles": 1,
        "percentile_list": PCT_LIST,
    }
    if a.data == "incompressible":
        o.update(refill_buffers=1, buffer_compress_percentage=0)
    else:
        o.update(zero_buffers=1)
    return o


def pick(override, default):
    return override if override else default


def point(name, **opts):
    return {"name": name, "opts": opts}


def build_prep(a):
    return [point("prep_seqwrite_1m", rw="write", bs="1M", iodepth=16, numjobs=1,
                  time_based=None, runtime=None, ramp_time=None,
                  lat_percentiles=None, percentile_list=None, loops=a.passes)]


def build_sanity(a):
    base = dict(rw="randread", bs="4k", iodepth=1, numjobs=1, size=a.sanity_size,
                ramp_time=max(a.ramp, 10))
    return [point("direct_4k_randread_qd1", direct=1, **base),
            point("buffered_4k_randread_qd1", direct=0, **base)]


def build_qd1(a):
    return [point("randread_4k_qd1", rw="randread", bs="4k", iodepth=1, numjobs=1),
            point("seqread_128k_qd1", rw="read", bs="128k", iodepth=1, numjobs=1),
            point("randwrite_4k_qd1", rw="randwrite", bs="4k", iodepth=1, numjobs=1),
            point("seqwrite_128k_qd1", rw="write", bs="128k", iodepth=1, numjobs=1)]


def build_bs(a):
    pts = []
    for rw in pick(a.rw, ["randread", "read"]):
        for bs in pick(a.bs, ["4k", "16k", "32k", "64k", "128k", "256k"]):
            for qd in pick(a.qd, [32]):
                for nj in pick(a.numjobs, [1]):
                    pts.append(point(f"{rw}_{bs}_qd{qd}_nj{nj}", rw=rw, bs=bs, iodepth=qd, numjobs=nj))
    return pts


def build_mix(a):
    pts = []
    bs = pick(a.bs, ["4k"])[0]
    pattern = "randrw" if pick(a.rw, ["randrw"])[0].startswith("rand") else "rw"
    for mix in pick(a.mix, [100, 70, 50, 0]):
        for qd in pick(a.qd, [32]):
            for nj in pick(a.numjobs, [1]):
                pts.append(point(f"{pattern}_{bs}_read{mix}_qd{qd}_nj{nj}", rw=pattern, rwmixread=mix,
                                 bs=bs, iodepth=qd, numjobs=nj))
    return pts


def build_qd(a):
    pts = []
    for rw in pick(a.rw, ["randread"]):
        bs = pick(a.bs, ["4k" if rw.startswith("rand") else "128k"])[0]
        for nj in pick(a.numjobs, [1]):
            for qd in pick(a.qd, [1, 2, 4, 8, 16, 32, 64, 128, 256]):
                pts.append(point(f"{rw}_{bs}_qd{qd}_nj{nj}", rw=rw, bs=bs, iodepth=qd, numjobs=nj))
    return pts


def build_peak(a):
    pts = []
    for rw in pick(a.rw, ["randread", "read"]):
        rand = rw.startswith("rand")
        bs = pick(a.bs, ["4k" if rand else "128k"])[0]
        for qd in pick(a.qd, [32, 128] if rand else [8, 32]):
            for nj in pick(a.numjobs, [1, 2, 4, 8] if rand else [1, 2, 4]):
                pts.append(point(f"{rw}_{bs}_qd{qd}_nj{nj}", rw=rw, bs=bs, iodepth=qd, numjobs=nj))
    return pts


def build_tail(a):
    pts = []
    for rw in pick(a.rw, ["randread"]):
        bs = pick(a.bs, ["4k"])[0]
        for qd in pick(a.qd, [16, 128]):
            for nj in pick(a.numjobs, [1]):
                pts.append(point(f"{rw}_{bs}_qd{qd}_nj{nj}", rw=rw, bs=bs, iodepth=qd, numjobs=nj))
    return pts


def build_range(a):
    pts = []
    file_bytes = parse_size(a.size)
    rw = pick(a.rw, ["randread"])[0]
    bs = pick(a.bs, ["4k"])[0]
    for r in pick(a.ranges, ["1G", "4G", "16G", "64G"]):
        if parse_size(r) > file_bytes:
            print(f"  skipping range {r}: larger than --size {a.size}")
            continue
        for qd in pick(a.qd, [32]):
            pts.append(point(f"{rw}_{bs}_range{r}_qd{qd}", rw=rw, bs=bs, iodepth=qd, numjobs=1, size=r))
    return pts


def build_steady(a):
    rw = pick(a.rw, ["write"])[0]
    bs = pick(a.bs, ["128k" if not rw.startswith("rand") else "4k"])[0]
    qd = pick(a.qd, [32])[0]
    nj = pick(a.numjobs, [1])[0]
    name = f"steady_{rw}_{bs}_qd{qd}_nj{nj}"
    return [point(name, rw=rw, bs=bs, iodepth=qd, numjobs=nj, ramp_time=0,
                  write_bw_log=name, write_lat_log=name, log_avg_msec=1000)]


# name: (builder, default reps, default runtime s, in 'all', description, hypothesis)
EXPERIMENTS = {
    "prep":   (build_prep, 1, None, False,
               "Fill the test file with sequential 1 MiB writes (required once before anything else).",
               "Burst sequential write of several GB/s; file is fully written so reads hit real flash."),
    "sanity": (build_sanity, 3, 30, True,
               "Pitfall demo: 4 KiB random read QD=1 on a small region, direct vs buffered I/O.",
               "Buffered reads come from the OS page cache and look 10-100x faster than direct I/O."),
    "qd1":    (build_qd1, 3, 30, True,
               "Zero-queue baselines: 4 KiB random read/write and 128 KiB sequential read/write at QD=1.",
               "4 KiB random read ~50-100 us; writes look faster (acked from controller buffer)."),
    "bs":     (build_bs, 3, 30, True,
               "Block-size sweep 4K-256K for random and sequential, fixed QD.",
               "IOPS falls and MB/s rises with block size until the ~7 GB/s PCIe Gen4 x4 ceiling."),
    "mix":    (build_mix, 3, 30, True,
               "Read/write mix sweep (100/70/50/0 % reads), fixed block size, pattern and QD.",
               "Mixed workloads underperform the average of pure read and pure write."),
    "qd":     (build_qd, 3, 30, True,
               "Queue-depth sweep 1-256 at fixed block size: throughput-vs-latency curve, knee, Little's Law.",
               "IOPS rises ~linearly at low QD, flattens at the knee; latency then grows ~linearly with QD."),
    "peak":   (build_peak, 3, 30, True,
               "Maximum IOPS and throughput: QD x numjobs grid for 4 KiB random and 128 KiB sequential.",
               "One submitting thread cannot saturate the drive; several jobs are needed for peak IOPS."),
    "tail":   (build_tail, 3, 120, True,
               "Tail latency (p50/p95/p99/p99.9) at mid QD and near-knee QD, longer runs.",
               "Near the knee p99/p99.9 grow much faster than p50 because of queueing."),
    "range":  (build_range, 3, 30, True,
               "Working-set / LBA-range effect: same random read over 1G..64G regions.",
               "Small ranges fit the controller's mapping cache and show lower latency."),
    "steady": (build_steady, 1, 300, False,
               "Device state: long sustained write logged per second to expose SLC-cache exhaustion. "
               "WRITES A LOT OF DATA - not part of 'all'.",
               "Bandwidth drops sharply once the SLC cache fills, then settles at steady state."),
}
ORDER = ["prep", "sanity", "qd1", "bs", "mix", "qd", "peak", "tail", "range", "steady"]


# --------------------------------------------------------------------------- #
# Job generation and execution
# --------------------------------------------------------------------------- #
def resolve(a, name):
    """Per-experiment defaults for knobs the user did not set."""
    _, reps, runtime, *_ = EXPERIMENTS[name]
    b = argparse.Namespace(**vars(a))
    b.reps = a.reps or reps
    b.runtime = a.runtime or runtime or 30
    return b


def job_text(name, opts):
    lines = [f"; generated by ssdbench.py {dt.datetime.now().isoformat(timespec='seconds')}",
             f"[{name}]"]
    lines += [f"{k}={v}" for k, v in opts.items() if v is not None]
    return "\n".join(lines) + "\n"


def make_jobs(a, name):
    jobs = []
    for p in EXPERIMENTS[name][0](a):
        opts = common_opts(a)
        opts.update(p["opts"])
        jobs.append((p["name"], opts))
    return jobs


def estimate(a, jobs):
    if a.runtime is None or any(o.get("time_based") is None for _, o in jobs):
        return None
    per = sum((o.get("runtime") or 0) + (o.get("ramp_time") or 0) for _, o in jobs)
    return a.reps * (per + a.cooldown * len(jobs))


def fmt_secs(s):
    return "unknown" if s is None else str(dt.timedelta(seconds=int(s)))


def quick_summary(path):
    try:
        t = path.read_text(errors="replace")
        d = json.loads(t[t.index("{"):])
    except (OSError, ValueError):
        return "  (could not parse output)"
    out = []
    for j in d["jobs"]:
        for k in ("read", "write"):
            s = j[k]
            if s.get("total_ios", 0) == 0:
                continue
            lat = s.get("lat_ns", {})
            p99 = lat.get("percentile", {}).get("99.000000", 0) / 1e3
            out.append(f"{k}: {s['iops']:,.0f} IOPS  {s['bw_bytes']/1e6:,.0f} MB/s  "
                       f"mean {lat.get('mean', 0)/1e3:,.1f} us  p99 {p99:,.1f} us")
    return "  " + " | ".join(out)


def preflight(a, names):
    bad = ("\\\\.\\", "physicaldrive", "/dev/")
    if any(b in a.file.lower() for b in bad):
        sys.exit("ERROR: raw devices are refused. Use a disposable test file.")
    f = local_path(a.file)
    if not a.dry_run and not f.parent.exists():
        sys.exit(f"ERROR: folder for test file does not exist: {f.parent}")
    if "prep" not in names and not a.dry_run:
        if not f.exists():
            sys.exit(f"ERROR: {a.file} not found. Run:  ssdbench.py run prep")
        if f.stat().st_size < parse_size(a.size):
            sys.exit(f"ERROR: {a.file} is smaller than --size {a.size}. Run prep with the same --size.")
    if "steady" in names and not (a.yes or a.dry_run):
        print("WARNING: 'steady' writes continuously for", a.runtime or 300,
              "s - possibly hundreds of GB to over 1 TB of SSD wear.")
        if input("Type 'yes' to continue: ").strip().lower() != "yes":
            sys.exit("Aborted.")


def run(a):
    names = ORDER[1:-1] if a.experiments == ["all"] else a.experiments
    names = [n for n in ORDER if n in names]
    preflight(a, names)
    fio = None if a.dry_run else find_fio(a.fio)
    version = "" if a.dry_run else subprocess.run([fio, "--version"], capture_output=True, text=True).stdout.strip()
    session = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    plans = []
    total = 0
    for n in names:
        b = resolve(a, n)
        jobs = make_jobs(b, n)
        est = estimate(b, jobs)
        total += est or 0
        plans.append((n, b, jobs, est))
        print(f"{n:7s} {len(jobs):3d} points x {b.reps} reps   est. {fmt_secs(est)}")
    print(f"Total estimated time: {fmt_secs(total)}  (prep/untimed runs not included)\n")

    for n, b, jobs, _ in plans:
        outdir = Path(a.outdir) / n / (session + (f"_{a.tag}" if a.tag else ""))
        if a.dry_run:
            for jn, opts in jobs:
                print(f"--- {n}/{jn}.fio ---\n{job_text(jn, opts)}")
            continue
        outdir.mkdir(parents=True, exist_ok=True)
        for jn, opts in jobs:
            (outdir / f"{jn}.fio").write_text(job_text(jn, opts))
        manifest = {"experiment": n, "session": session, "tag": a.tag, "fio": fio, "fio_version": version,
                    "description": EXPERIMENTS[n][4], "hypothesis": EXPERIMENTS[n][5],
                    "knobs": {k: v for k, v in vars(b).items() if k not in ("func",)},
                    "argv": sys.argv, "runs": []}
        try:
            for r in range(1, b.reps + 1):
                order = list(jobs)
                if a.shuffle:
                    random.shuffle(order)
                for i, (jn, _) in enumerate(order):
                    out = f"{jn}_r{r}.json"
                    print(f"[{n}] rep {r}/{b.reps}  {jn}")
                    start = dt.datetime.now().isoformat()
                    rc = subprocess.run([fio, f"{jn}.fio", "--output-format=json", f"--output={out}"],
                                        cwd=outdir).returncode
                    manifest["runs"].append({"job": jn, "rep": r, "start": start,
                                             "end": dt.datetime.now().isoformat(), "returncode": rc,
                                             "output": out})
                    if rc != 0:
                        print(f"  fio exited with code {rc}")
                    else:
                        print("\r" + " " * 70 + "\r" + quick_summary(outdir / out))
                    last = r == b.reps and i == len(order) - 1
                    if a.cooldown and not last:
                        time.sleep(a.cooldown)
        except KeyboardInterrupt:
            print("\nInterrupted - saving manifest for completed runs.")
            (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
            sys.exit(1)
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        print(f"Saved to {outdir}\n")


def list_cmd(a):
    print(f"{'experiment':10s} {'points':>6s} {'reps':>4s} {'est. time':>10s}  description")
    for n in ORDER:
        b = resolve(a, n)
        jobs = make_jobs(b, n)
        flag = "" if EXPERIMENTS[n][3] else "  [not in 'all']"
        print(f"{n:10s} {len(jobs):6d} {b.reps:4d} {fmt_secs(estimate(b, jobs)):>10s}  {EXPERIMENTS[n][4]}{flag}")
        print(f"{'':34s}hypothesis: {EXPERIMENTS[n][5]}")


def parse_cmd(a):
    sys.path.insert(0, str(ROOT / "analysis"))
    import parse_fio
    parse_fio.main()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
class Fmt(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    def _get_help_string(self, action):
        if action.default is None or action.default is False:
            return action.help
        return super()._get_help_string(action)


EXAMPLES = """
examples:
  ssdbench.py list                                   show experiments, points and time estimates
  ssdbench.py run prep                               create/fill the 64 GiB test file (once)
  ssdbench.py run sanity qd1                         pitfall demo + zero-queue baselines
  ssdbench.py run qd --numjobs 1,4                   QD sweep with 1 and 4 jobs
  ssdbench.py run bs --rw randread,read,randwrite,write --bs 4k,16k,32k,64k,128k,256k,512k,1m
  ssdbench.py run tail --qd 8,64 --runtime 180       tail latency at your mid/knee QD
  ssdbench.py run steady --runtime 180 --yes         sustained write (heavy SSD wear)
  ssdbench.py run all --dry-run                      print every generated job file, run nothing
  ssdbench.py parse                                  build results/processed/summary.csv + summary_agg.csv
"""


def build_parser():
    p = argparse.ArgumentParser(prog="ssdbench.py", description=__doc__, epilog=EXAMPLES, formatter_class=Fmt)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{list,run,parse}")

    def knobs(sp):
        g = sp.add_argument_group("target and safety")
        g.add_argument("--file", default="C:\\fiotest\\testfile" if windows_target() else "/mnt/fiotest/testfile",
                       help="disposable test file (raw devices are refused)")
        g.add_argument("--size", default="64G", help="test file size = maximum LBA range tested")
        g.add_argument("--fio", help="path to fio executable (auto-detected if omitted)")
        g.add_argument("--ioengine", default="windowsaio" if windows_target() else "libaio",
                       help="fio I/O engine; must be asynchronous for QD>1 to be real")
        g = sp.add_argument_group("timing and repetition")
        g.add_argument("--runtime", type=int, help="seconds per run (default: 30, tail 120, steady 300)")
        g.add_argument("--ramp", type=int, default=5, help="warm-up seconds excluded from stats")
        g.add_argument("--reps", type=int, help="repetitions per point (default: 3, prep/steady 1)")
        g.add_argument("--cooldown", type=int, default=10, help="idle seconds between runs (thermal)")
        g.add_argument("--shuffle", action="store_true", help="randomize point order within each rep")
        g = sp.add_argument_group("workload knobs (comma lists; override each experiment's defaults)")
        g.add_argument("--bs", type=csv_list(), help="block sizes, e.g. 4k,16k,128k")
        g.add_argument("--qd", type=csv_list(int), help="iodepth values, e.g. 1,2,4,...,256")
        g.add_argument("--numjobs", type=csv_list(int), help="parallel jobs (threads), e.g. 1,2,4")
        g.add_argument("--rw", type=csv_list(), help="patterns: randread,read,randwrite,write,randrw,rw")
        g.add_argument("--mix", type=csv_list(int), help="read percentages for 'mix', e.g. 100,70,50,0")
        g.add_argument("--ranges", type=csv_list(), help="LBA ranges for 'range', e.g. 1G,4G,16G,64G")
        g.add_argument("--data", choices=["incompressible", "zeros"], default="incompressible",
                       help="write data pattern (keep consistent; document it)")
        g.add_argument("--sanity-size", default="1G", help="region size for the buffered-vs-direct demo")
        g.add_argument("--passes", type=int, default=1, help="number of full-file passes for 'prep'")

    sp = sub.add_parser("list", help="list experiments with point counts and time estimates", formatter_class=Fmt)
    knobs(sp)
    sp.set_defaults(func=list_cmd)

    sp = sub.add_parser("run", help="run one or more experiments", formatter_class=Fmt, epilog=EXAMPLES)
    sp.add_argument("experiments", nargs="+", choices=ORDER + ["all"],
                    help="experiments to run ('all' = everything except prep and steady)")
    knobs(sp)
    g = sp.add_argument_group("output")
    g.add_argument("--outdir", default=str(ROOT / "results" / "raw"), help="where results are written")
    g.add_argument("--tag", help="label appended to the session folder, e.g. 'after_reboot'")
    g.add_argument("--dry-run", action="store_true", help="print generated job files and exit")
    g.add_argument("--yes", action="store_true", help="skip the confirmation for 'steady'")
    sp.set_defaults(func=run)

    sp = sub.add_parser("parse", help="parse all JSON results into CSV summaries", formatter_class=Fmt)
    sp.set_defaults(func=parse_cmd)
    return p


def main():
    a = build_parser().parse_args()
    if getattr(a, "experiments", None) and "all" in a.experiments:
        a.experiments = ["all"]
    a.func(a)


if __name__ == "__main__":
    main()

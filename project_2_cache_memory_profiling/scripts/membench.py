#!/usr/bin/env python3
"""
membench - run the ECSE 6320 Project 2 cache & memory experiment matrix.

Every point runs one of the two C benchmarks (src/pchase.c for latency,
src/bwbench.c for bandwidth) and saves its CSV output, stderr log and the exact
command under results/raw/<experiment>/<session>/, together with a manifest
(knobs, hypothesis, compiler/perf versions, timestamps) and an environment
snapshot, so each result can be reproduced exactly.

Run on the Linux test machine from the project folder, after `make`.
Benchmarks: src/pchase.c (latency), src/bwbench.c (bandwidth), src/saxpy.c (cache-miss impact).
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
PCHASE = ROOT / "pchase"
BWBENCH = ROOT / "bwbench"
SAXPY = ROOT / "saxpy"
ENV_SCRIPT = ROOT / "scripts" / "env_capture.sh"
PERF_HOME = Path.home() / "tools" / "perf"


def csv_list(cast=str):
    def f(text):
        return [cast(x.strip()) for x in text.split(",") if x.strip()]
    return f


def pick(override, default):
    return override if override else default


# --------------------------------------------------------------------------- #
# Experiment definitions
# Each point: {"name", "tool": "pchase"|"bwbench", "args": [...], optional "perf": [events]}
# --------------------------------------------------------------------------- #
def point(name, tool, args, perf=None, load=None, **extra):
    """load = bwbench args for a background load that runs while this point is measured."""
    return {"name": name, "tool": tool, "args": [str(x) for x in args], "perf": perf,
            "load": [str(x) for x in load] if load else None, **extra}


WS_SIZES = ["4K", "8K", "16K", "24K", "32K", "40K", "48K", "56K", "64K", "96K", "128K", "192K",
            "256K", "384K", "512K", "768K", "1M", "1280K", "1536K", "2M", "3M", "4M", "6M", "8M",
            "12M", "16M", "24M", "28M", "32M", "40M", "48M", "64M", "96M", "128M", "256M", "512M", "1G"]
# pchase counts cycles, L1D and dTLB misses itself, around the timed loop only.
# A point can still set perf=[events] to wrap the whole process in `perf stat`.


def build_sanity(a):
    """Pitfall demos: (1) sequential pointer chase hides DRAM latency via the prefetcher,
    (2) THP=always silently turns a '4 KiB page' TLB test into a 2 MiB-page test."""
    c = a.cpu
    return [point("chase_1G_rand", "pchase", ["-s", "1G", "-p", "rand", "-c", c, "-r", a.reps, "-n", "20M"]),
            point("chase_1G_seq", "pchase", ["-s", "1G", "-p", "seq", "-c", c, "-r", a.reps, "-n", "20M"]),
            point("tlb_512M_pagedefault", "pchase", ["-s", "512M", "-S", 4096, "-P", "thp", "-c", c,
                                                     "-r", a.reps, "-n", "5M"]),
            point("tlb_512M_page4k", "pchase", ["-s", "512M", "-S", 4096, "-P", "4k", "-c", c,
                                                "-r", a.reps, "-n", "5M"])]


def build_baseline(a):
    pts = []
    for lvl, size in [("L1", "32K"), ("L2", "512K"), ("L3", "16M"), ("DRAM", "1G")]:
        pts.append(point(f"{lvl}_{size}", "pchase", ["-s", size, "-k", 1, "-p", "rand", "-c", a.cpu,
                                                     "-r", a.reps, "-n", "20M"], level=lvl))
    return pts


def build_ws(a):
    return [point(f"ws_{s}", "pchase", ["-s", s, "-k", 1, "-p", "rand", "-c", a.cpu, "-r", a.reps])
            for s in pick(a.sizes, WS_SIZES)]


def build_pattern(a):
    pts = []
    size = pick(a.sizes, ["1G"])[0]
    for p in ["seq", "rand"]:
        for s in pick(a.strides, [64, 256, 1024]):
            pts.append(point(f"lat_{p}_s{s}", "pchase", ["-s", size, "-S", s, "-p", p, "-c", a.cpu,
                                                         "-r", a.reps, "-n", "20M"]))
            pts.append(point(f"bw_{p}_s{s}", "bwbench", ["-s", size, "-S", s, "-p", p, "-m", 100,
                                                         "-t", 1, "-c", a.cpu, "-r", a.reps]))
    return pts


def build_rw(a):
    pts = []
    size = pick(a.sizes, ["1G"])[0]
    for t in pick(a.threads, [1, 16]):
        for m in pick(a.mix, [100, 70, 50, 0]):
            pts.append(point(f"rw_read{m}_t{t}", "bwbench", ["-s", size, "-S", 64, "-p", "seq", "-m", m,
                                                             "-t", t, "-c", a.cpus, "-r", a.reps, "-b", "8G"]))
    return pts


def build_mlp(a):
    """Intensity sweep, part 1: one thread, k independent pointer chains in flight."""
    size = pick(a.sizes, ["1G"])[0]
    return [point(f"mlp_k{k}", "pchase", ["-s", size, "-k", k, "-p", "rand", "-c", a.cpu,
                                         "-r", a.reps, "-n", "20M"])
            for k in pick(a.chains, [1, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64])]


def build_loaded(a):
    """Intensity sweep, part 2 (loaded latency): pchase k=1 on one core measures latency
    while bwbench on N other cores generates background bandwidth."""
    size = pick(a.sizes, ["1G"])[0]
    pts = []
    for n in pick(a.threads, [0, 1, 2, 4, 6, 8, 10, 12, 14]):
        lat = ["-s", size, "-k", 1, "-p", "rand", "-c", a.lat_cpu, "-r", a.reps, "-n", "10M"]
        load = None
        if n > 0:
            load = ["-s", f"{256 * n}M", "-S", 64, "-p", "seq", "-m", 100, "-t", n, "-c", a.bw_cpus,
                    "-r", 100000, "-b", "1G"]
        pts.append(point(f"loaded_bw{n}", "pchase", lat, load=load, load_threads=n))
    return pts


def build_tlb(a):
    pts = []
    for s in pick(a.sizes, ["4M", "16M", "64M", "256M", "1G"]):
        for pg in ["4k", "huge"]:
            pts.append(point(f"tlb_{s}_{pg}", "pchase", ["-s", s, "-S", 4096, "-P", pg, "-p", "rand",
                                                         "-c", a.cpu, "-r", a.reps, "-n", "5M"]))
    return pts


def build_saxpy(a):
    """Cache-miss impact: same SAXPY arithmetic, footprint from L1 to DRAM, seq vs rand order."""
    pts = []
    for size in pick(a.sizes, ["16K", "32K", "128K", "512K", "2M", "8M", "16M", "48M", "128M", "512M", "1G"]):
        for p in ["seq", "rand"]:
            pts.append(point(f"saxpy_{p}_{size}", "saxpy", ["-s", size, "-p", p, "-c", a.cpu, "-r", a.reps]))
    return pts


# name: (builder, default reps, description, hypothesis)
EXPERIMENTS = {
    "sanity":   (build_sanity, 5,
                 "Pitfall demos: sequential vs random pointer chase at 1 GiB; THP default vs forced 4 KiB "
                 "pages in a one-access-per-page test.",
                 "Sequential chase looks several times faster than random (prefetcher); with THP=always "
                 "the 'default page' run shows few dTLB misses, the forced-4 KiB run many."),
    "baseline": (build_baseline, 10,
                 "Zero-queue baselines: dependent random pointer chase, one load in flight, at 32 KiB, "
                 "512 KiB, 16 MiB and 1 GiB (L1, L2, L3, DRAM).",
                 "L1 ~4 cycles, L2 ~14 cycles, L3 ~50 cycles, DRAM ~80-100 ns."),
    "ws":       (build_ws, 5,
                 "Working-set sweep 4 KiB-1 GiB, random pointer chase: the latency staircase.",
                 "Flat plateaus with steps just past 48 KiB (L1), 1 MiB (L2) and 32 MiB (one CCD's L3)."),
    "pattern":  (build_pattern, 5,
                 "Pattern x stride sweep at 1 GiB: seq vs rand, 64/256/1024 B; latency (pchase) and "
                 "bandwidth (bwbench, 1 thread).",
                 "Sequential much faster than random at 64 B; the gap shrinks as stride grows and "
                 "prefetching weakens."),
    "rw":       (build_rw, 5,
                 "Read/write mix sweep: 100/70/50/0 % reads, sequential 64 B, 1 GiB, 1 and 16 threads.",
                 "Bandwidth falls as the write share rises (read-for-ownership and write-back traffic)."),
    "mlp":      (build_mlp, 5,
                 "Intensity sweep part 1: 1 thread with 1-64 independent pointer chains (memory-level "
                 "parallelism) at 1 GiB.",
                 "Throughput rises ~linearly with chains, then flattens at the core's miss-handling "
                 "limit while per-chain latency rises (the knee)."),
    "loaded":   (build_loaded, 5,
                 "Intensity sweep part 2: latency of a single chain on one core while 0-14 other cores "
                 "stream reads (loaded latency).",
                 "Latency stays near idle until DRAM bandwidth nears its peak, then rises sharply."),
    "tlb":      (build_tlb, 5,
                 "TLB-miss impact: one access per 4 KiB page, random, 4 MiB-1 GiB, 4 KiB vs 2 MiB pages, "
                 "with dTLB counters.",
                 "With 4 KiB pages, latency and dTLB misses jump once pages exceed the TLB reach; "
                 "2 MiB pages remove most misses."),
    "saxpy":    (build_saxpy, 5,
                 "Cache-miss impact: SAXPY y = a*x + y, footprint 16 KiB-1 GiB, sequential (vectorized) vs "
                 "shuffled-index order, with L1D / LLC / dTLB miss counters.",
                 "Time per element tracks misses per element: flat while x and y fit in cache, rising with "
                 "LLC misses; random order far slower at DRAM sizes."),
}
ORDER = ["sanity", "baseline", "ws", "pattern", "rw", "mlp", "loaded", "tlb", "saxpy"]


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def perf_cmd():
    exe = shutil.which("perf") or str(PERF_HOME / "usr" / "bin" / "perf")
    env = dict(os.environ)
    lib = PERF_HOME / "usr" / "lib"
    if lib.exists():
        env["LD_LIBRARY_PATH"] = f"{lib}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")
    return exe, env


def tool_version(cmd, env=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, env=env).stdout.splitlines()[0]
    except (OSError, IndexError):
        return "unavailable"


def resolve(a, name):
    b = argparse.Namespace(**vars(a))
    b.reps = a.reps or EXPERIMENTS[name][1]
    return b


def run_point(p, outdir, perf):
    tool = {"pchase": PCHASE, "bwbench": BWBENCH, "saxpy": SAXPY}[p["tool"]]
    cmd = [str(tool), "-H"] + p["args"]
    env = None
    if p.get("perf"):
        exe, env = perf
        cmd = [exe, "stat", "-x", ",", "-o", f"{p['name']}_perf.csv", "-e", ",".join(p["perf"]), "--"] + cmd
    loader = None
    if p.get("load"):
        loader = subprocess.Popen([str(BWBENCH), "-H"] + p["load"], cwd=outdir,
                                  stdout=open(outdir / f"{p['name']}_load.csv", "w"),
                                  stderr=open(outdir / f"{p['name']}_load.log", "w"))
        time.sleep(1.5)  # let the background threads allocate, first-touch and reach steady state
    with open(outdir / f"{p['name']}.csv", "w") as out, open(outdir / f"{p['name']}.log", "w") as err:
        rc = subprocess.run(cmd, cwd=outdir, stdout=out, stderr=err, env=env).returncode
    if loader:
        loader.terminate()
        loader.wait()
    return cmd, rc


def quick_summary(path):
    try:
        lines = path.read_text().strip().splitlines()
        hdr = lines[0].split(",")
        rows = [dict(zip(hdr, l.split(","))) for l in lines[1:]]
    except (OSError, IndexError):
        return "  (no output)"
    if not rows:
        return "  (no output)"
    if "ns_per_load" in hdr:
        ns = sorted(float(r["ns_per_load"]) for r in rows)
        cy = sorted(float(r["cycles_per_load"]) for r in rows)
        return f"  median {ns[len(ns) // 2]:.2f} ns/load, {cy[len(cy) // 2]:.1f} cycles/load"
    if "ns_per_elem" in hdr:
        ns = sorted(float(r["ns_per_elem"]) for r in rows)
        return f"  median {ns[len(ns) // 2]:.3f} ns/element"
    gb = sorted(float(r["gb_per_s"]) for r in rows)
    return f"  median {gb[len(gb) // 2]:.2f} GB/s"


def preflight():
    missing = [t.name for t in (PCHASE, BWBENCH, SAXPY) if not t.exists()]
    if missing:
        sys.exit(f"ERROR: {', '.join(missing)} not built. Run: make")
    if sys.platform != "linux":
        sys.exit("ERROR: run this on the Linux test machine.")


def run(a):
    names = [n for n in ORDER if n in (ORDER if a.experiments == ["all"] else a.experiments)]
    if not a.dry_run:
        preflight()
    perf = perf_cmd()
    session = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    plans = [(n, resolve(a, n)) for n in names]
    plans = [(n, b, EXPERIMENTS[n][0](b)) for n, b in plans]
    for n, b, pts in plans:
        print(f"{n:9s} {len(pts):3d} points x {b.reps} reps")
    print()

    for n, b, pts in plans:
        outdir = Path(a.outdir) / n / (session + (f"_{a.tag}" if a.tag else ""))
        if a.dry_run:
            for p in pts:
                tool = "./" + p["tool"]
                pre = f"perf stat -e {','.join(p['perf'])} -- " if p.get("perf") else ""
                bg = f"   [background: ./bwbench {' '.join(p['load'])}]" if p.get("load") else ""
                print(f"{n}/{p['name']}: {pre}{tool} {' '.join(p['args'])}{bg}")
            continue
        outdir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["bash", str(ENV_SCRIPT), str(outdir / "env.txt")], stdout=subprocess.DEVNULL)
        manifest = {"experiment": n, "session": session, "tag": a.tag,
                    "description": EXPERIMENTS[n][2], "hypothesis": EXPERIMENTS[n][3],
                    "gcc": tool_version(["gcc", "--version"]),
                    "perf": tool_version([perf[0], "--version"], perf[1]),
                    "uptime": tool_version(["uptime"]),
                    "knobs": {k: v for k, v in vars(b).items() if k != "func"},
                    "argv": sys.argv, "points": pts, "runs": []}
        order = list(pts)
        if a.shuffle:
            random.shuffle(order)
        try:
            for i, p in enumerate(order):
                print(f"[{n}] {i + 1}/{len(order)}  {p['name']}")
                start = dt.datetime.now().isoformat()
                cmd, rc = run_point(p, outdir, perf)
                manifest["runs"].append({"point": p["name"], "cmd": cmd, "start": start,
                                         "end": dt.datetime.now().isoformat(), "returncode": rc})
                print(f"  exit code {rc}" if rc else quick_summary(outdir / f"{p['name']}.csv"))
                if a.cooldown and i < len(order) - 1:
                    time.sleep(a.cooldown)
        except KeyboardInterrupt:
            print("\nInterrupted - saving manifest for completed points.")
            (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
            sys.exit(1)
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        print(f"Saved to {outdir}\n")


def list_cmd(a):
    print(f"{'experiment':10s} {'points':>6s} {'reps':>4s}  description")
    for n in ORDER:
        b = resolve(a, n)
        print(f"{n:10s} {len(EXPERIMENTS[n][0](b)):6d} {b.reps:4d}  {EXPERIMENTS[n][2]}")
        print(f"{'':23s}hypothesis: {EXPERIMENTS[n][3]}")


def env_cmd(a):
    out = ROOT / "env" / f"system_info_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    out.parent.mkdir(exist_ok=True)
    subprocess.run(["bash", str(ENV_SCRIPT), str(out)])


def parse_cmd(a):
    sys.path.insert(0, str(ROOT / "analysis"))
    import parse_results
    parse_results.main()


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
  membench.py list                          show experiments, points and hypotheses
  membench.py env                           save env/system_info_<time>.txt
  membench.py run baseline ws               zero-queue baselines + working-set sweep
  membench.py run pattern rw --shuffle      pattern/stride and read/write mix sweeps
  membench.py run mlp loaded                intensity sweep (knee)
  membench.py run tlb sanity                TLB impact + pitfall demos
  membench.py run saxpy                     cache-miss impact on a real kernel
  membench.py run ws --sizes 16K,1M,64M     override sizes
  membench.py run all --dry-run             print every command, run nothing
  membench.py parse                         build results/processed/summary*.csv
"""


def build_parser():
    p = argparse.ArgumentParser(prog="membench.py", description=__doc__, epilog=EXAMPLES, formatter_class=Fmt)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="{list,run,env,parse}")

    def knobs(sp):
        g = sp.add_argument_group("placement (CCD 0 = CPUs 0-7, CCD 1 = CPUs 8-15; 16-31 are SMT siblings)")
        g.add_argument("--cpu", type=int, default=2, help="CPU for single-thread runs")
        g.add_argument("--cpus", default="2-7,0,1,8-15", help="CPU order for multi-thread bwbench runs")
        g.add_argument("--lat-cpu", type=int, default=15, help="'loaded': CPU for the latency probe")
        g.add_argument("--bw-cpus", default="0-14", help="'loaded': CPUs for the background load")
        g = sp.add_argument_group("repetition")
        g.add_argument("--reps", type=int, help="repetitions per point (default: 5, baseline 10)")
        g.add_argument("--cooldown", type=int, default=1, help="idle seconds between points")
        g.add_argument("--shuffle", action="store_true", help="randomize point order")
        g = sp.add_argument_group("sweep knobs (comma lists; override each experiment's defaults)")
        g.add_argument("--sizes", type=csv_list(), help="working-set sizes, e.g. 32K,1M,1G")
        g.add_argument("--strides", type=csv_list(int), help="strides in bytes for 'pattern'")
        g.add_argument("--mix", type=csv_list(int), help="read percentages for 'rw'")
        g.add_argument("--threads", type=csv_list(int), help="thread counts for 'rw' / 'loaded'")
        g.add_argument("--chains", type=csv_list(int), help="chain counts for 'mlp'")

    sp = sub.add_parser("list", help="list experiments and hypotheses", formatter_class=Fmt)
    knobs(sp)
    sp.set_defaults(func=list_cmd)

    sp = sub.add_parser("run", help="run one or more experiments", formatter_class=Fmt, epilog=EXAMPLES)
    sp.add_argument("experiments", nargs="+", choices=ORDER + ["all"], help="experiments to run")
    knobs(sp)
    g = sp.add_argument_group("output")
    g.add_argument("--outdir", default=str(ROOT / "results" / "raw"), help="where results are written")
    g.add_argument("--tag", help="label appended to the session folder")
    g.add_argument("--dry-run", action="store_true", help="print the commands and exit")
    sp.set_defaults(func=run)

    sp = sub.add_parser("env", help="save a system snapshot to env/", formatter_class=Fmt)
    sp.set_defaults(func=env_cmd)
    sp = sub.add_parser("parse", help="parse all results into CSV summaries", formatter_class=Fmt)
    sp.set_defaults(func=parse_cmd)
    return p


def main():
    a = build_parser().parse_args()
    if getattr(a, "experiments", None) and "all" in a.experiments:
        a.experiments = ["all"]
    a.func(a)


if __name__ == "__main__":
    main()
